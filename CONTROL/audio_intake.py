"""Disk-backed audio intake. No decoding, processing, or Logic automation.

One server process owns this store. A global nonblocking lock bounds concurrent
uploads/extraction; .part files are never published as originals or ready audio.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import threading
import unicodedata
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

AUDIO = {'.wav', '.aif', '.aiff', '.mp3'}
SUPPORTED = AUDIO | {'.zip'}
CHUNK = 1024 * 1024


class IntakeError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def safe_name(name, single=False):
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise IntakeError('Empty or excessively long filename')
    if any(ord(c) < 32 or 0xd800 <= ord(c) <= 0xdfff or ord(c) == 127 for c in name) or '\\' in name or ':' in name:
        raise IntakeError('Unsafe filename characters')
    if len(name.encode('utf-8')) > 1024:
        raise IntakeError('Excessively long filename')
    parts = name.rstrip('/').split('/')
    if single and len(parts) != 1:
        raise IntakeError('Upload name must be a filename, not a path')
    if len(parts) > 24 or any(p in {'', '.', '..'} or p.endswith((' ', '.')) or len(p.encode('utf-8')) > 240 for p in parts):
        raise IntakeError('Unsafe path, traversal, or excessive path depth')
    return parts[-1]


def audio_header(path):
    with path.open('rb') as source:
        head = source.read(12)
    ext = path.suffix.lower()
    valid = ((ext == '.wav' and head[:4] in {b'RIFF', b'RF64'} and head[8:12] == b'WAVE')
             or (ext in {'.aif', '.aiff'} and head[:4] == b'FORM' and head[8:12] in {b'AIFF', b'AIFC'})
             or (ext == '.mp3' and (head[:3] == b'ID3' or (len(head) >= 2 and head[0] == 255 and head[1] & 0xe0 == 0xe0))))
    if not valid:
        raise IntakeError('File header does not match its audio extension')


def bounded_zip_directory(path, max_entries, max_directory):
    """Bound zipfile's central-directory allocation, including ZIP64 archives."""
    size = path.stat().st_size
    with path.open('rb') as source:
        source.seek(max(0, size - 65557))
        tail = source.read(65557)
        pos = tail.rfind(b'PK\x05\x06')
        if pos < 0 or pos + 22 > len(tail):
            raise IntakeError('Corrupt ZIP: missing end record')
        _, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack_from('<4s4H2LH', tail, pos)
        eocd = size - len(tail) + pos
        if pos + 22 + comment != len(tail) or disk or cd_disk or disk_count != count:
            raise IntakeError('Corrupt or multi-disk ZIP is unsupported')
        if count == 65535 or cd_size == 0xffffffff or offset == 0xffffffff:
            if eocd < 20:
                raise IntakeError('Corrupt ZIP64 locator')
            source.seek(eocd - 20)
            locator = source.read(20)
            sig, disk, record, disks = struct.unpack('<4sLQL', locator)
            if sig != b'PK\x06\x07' or disk or disks != 1 or record + 56 > eocd - 20:
                raise IntakeError('Unsupported ZIP64 layout')
            source.seek(record)
            fields = struct.unpack('<4sQ2H2L4Q', source.read(56))
            sig, record_size, _, _, disk, cd_disk, disk_count, count, cd_size, offset = fields
            if sig != b'PK\x06\x06' or disk or cd_disk or disk_count != count or record_size != 44:
                raise IntakeError('Unsupported ZIP64 end record')
        if count > max_entries or cd_size > max_directory:
            raise IntakeError('ZIP has too many entries or an oversized directory', 413)
        if offset + cd_size > eocd:
            raise IntakeError('Corrupt ZIP directory bounds')
        source.seek(offset)
        consumed, actual_count = 0, 0
        while consumed < cd_size:
            header = source.read(46)
            if len(header) != 46 or header[:4] != b'PK\x01\x02':
                raise IntakeError('Corrupt ZIP directory entry')
            name_size, extra_size, comment_size = struct.unpack_from('<3H', header, 28)
            consumed += 46 + name_size + extra_size + comment_size
            actual_count += 1
            if consumed > cd_size or actual_count > max_entries:
                raise IntakeError('ZIP directory entry limit or bounds exceeded', 413)
            source.seek(name_size + extra_size + comment_size, 1)
        if actual_count != count:
            raise IntakeError('ZIP directory entry count mismatch')


class IntakeStore:
    def __init__(self, root, *, max_file=2 * 1024**3, max_batch=8 * 1024**3,
                 max_expanded=8 * 1024**3, max_staged=16 * 1024**3,
                 max_entries=2048, max_directory=8 * 1024**2, max_ratio=1000):
        self.root = Path(root).expanduser().resolve()
        self.max_file, self.max_batch = max_file, max_batch
        self.max_expanded, self.max_staged = max_expanded, max_staged
        self.max_entries, self.max_directory, self.max_ratio = max_entries, max_directory, max_ratio
        self.lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Recovery occurs only at process startup, before requests are served.
        for manifest in self.root.glob('*/manifest.json'):
            batch = self._load(manifest.parent.name)
            changed = False
            for item in batch['files']:
                if item['status'] == 'receiving':
                    item.update(status='interrupted', reason='Server stopped during import; retry this file')
                    self._discard_audio(manifest.parent, item)
                    for entry in item['entries']:
                        if entry['status'] == 'accepted':
                            entry.update(status='interrupted', reason='Working copy removed during restart recovery')
                            entry.pop('path', None)
                    changed = True
            for part in manifest.parent.glob('originals/*/*.part'):
                part.unlink()
            if changed:
                self._save(batch)

    def config(self):
        return {'staging_root': str(self.root), 'max_file_bytes': self.max_file,
                'max_batch_bytes': self.max_batch, 'max_expanded_bytes': self.max_expanded,
                'max_staged_bytes': self.max_staged, 'max_zip_entries': self.max_entries,
                'max_zip_directory_bytes': self.max_directory, 'max_compression_ratio': self.max_ratio,
                'max_files': 128, 'stream_chunk_bytes': CHUNK,
                'audio_validation': 'container header only; decode and listening not verified',
                'processing': 'not connected', 'logic_project': 'not generated'}

    def _dir(self, batch_id):
        if not re.fullmatch('[0-9a-f]{32}', batch_id):
            raise IntakeError('Invalid batch ID', 404)
        return self.root / batch_id

    def _load(self, batch_id):
        try:
            return json.loads((self._dir(batch_id) / 'manifest.json').read_text())
        except FileNotFoundError as exc:
            raise IntakeError('Batch not found', 404) from exc

    def _save(self, batch):
        batch['complete'] = all(f['status'] in {'accepted', 'rejected'} for f in batch['files'])
        batch['ready'] = batch['complete'] and any(f['status'] == 'accepted' for f in batch['files'])
        path = self._dir(batch['id'])
        temp = path / 'manifest.tmp'
        with temp.open('w') as target:
            json.dump(batch, target, indent=2, ensure_ascii=True)
            target.flush()
            os.fsync(target.fileno())
        temp.replace(path / 'manifest.json')

    def receipt(self, batch_id):
        batch = self._load(batch_id)
        batch['staging_path'] = str(self._dir(batch_id))
        batch['complete'] = all(f['status'] in {'accepted', 'rejected'} for f in batch['files'])
        batch['ready'] = batch['complete'] and any(f['status'] == 'accepted' for f in batch['files'])
        return batch

    def create(self, files):
        if not isinstance(files, list) or not 1 <= len(files) <= 128:
            raise IntakeError('Select between 1 and 128 files')
        if not self.lock.acquire(blocking=False):
            raise IntakeError('Another import is active; retry shortly', 409)
        try:
            items = []
            total = 0
            for index, f in enumerate(files):
                if not isinstance(f, dict) or type(f.get('size')) is not int or f['size'] < 0:
                    raise IntakeError('Each file needs a name and nonnegative integer size')
                name = f.get('name')
                reason = None
                try:
                    safe_name(name, single=True)
                    if Path(name).suffix.lower() not in SUPPORTED:
                        raise IntakeError('Unsupported type: use ZIP, WAV, AIFF, AIF, or MP3')
                    if not 0 < f['size'] <= self.max_file:
                        raise IntakeError('Empty file or upload exceeds per-file size limit', 413)
                except IntakeError as exc:
                    reason = str(exc)
                # Bound metadata even for rejected names.
                display_name = name[:1024] if isinstance(name, str) else '(missing name)'
                items.append({'index': index, 'name': display_name, 'size': f['size'],
                              'status': 'rejected' if reason else 'pending', 'reason': reason,
                              'entries': []})
                if not reason:
                    total += f['size']
            if total > self.max_batch:
                raise IntakeError('Selection exceeds batch upload limit; split the drop', 413)
            batch = {'schema': 'juice.audio-intake/v1', 'id': uuid.uuid4().hex,
                     'created_at': datetime.now(timezone.utc).isoformat(),
                     'workflow': 'flood-my-ears', 'processing': 'not connected',
                     'logic_project': 'not generated', 'files': items}
            self._dir(batch['id']).mkdir(mode=0o700)
            self._save(batch)
            return self.receipt(batch['id'])
        finally:
            self.lock.release()

    def _discard_audio(self, base, item):
        shutil.rmtree(base / 'audio' / f"{item['index']:04d}", ignore_errors=True)

    def upload(self, batch_id, index, stream, length):
        if not self.lock.acquire(blocking=False):
            raise IntakeError('Another import is active; retry shortly', 409)
        try:
            batch = self._load(batch_id)
            if index < 0 or index >= len(batch['files']):
                raise IntakeError('File index not found', 404)
            item = batch['files'][index]
            if item['status'] not in {'pending', 'interrupted'}:
                raise IntakeError('File already completed; consult its receipt', 409)
            if length != item['size'] or length > self.max_file:
                raise IntakeError('Content-Length does not match declared file size', 413)
            base = self._dir(batch_id)
            dest = base / 'originals' / f'{index:04d}'
            dest.mkdir(parents=True, exist_ok=True, mode=0o700)
            original = dest / item['name']
            part = dest / 'upload.part'
            self._require_space(length)
            item.update(status='receiving', reason=None, entries=[])
            self._save(batch)
            try:
                # A complete original can survive a process stop before manifest update.
                # It is never overwritten; retry compares the incoming bytes first.
                digest, count = hashlib.sha256(), 0
                with part.open('xb') as target:
                    while count < length:
                        chunk = stream.read(min(CHUNK, length - count))
                        if not chunk:
                            raise IntakeError('Interrupted upload: fewer bytes than declared')
                        count += len(chunk)
                        target.write(chunk)
                        digest.update(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                if original.exists():
                    if original.stat().st_size != count or self._hash(original) != digest.hexdigest():
                        raise IntakeError('Retry differs from preserved original; create a new batch')
                    part.unlink()
                else:
                    part.replace(original)
                    original.chmod(0o400)
                item.update(original=str(original.relative_to(base)), sha256=digest.hexdigest())
                self._save(batch)
            except (OSError, IntakeError) as exc:
                part.unlink(missing_ok=True)
                item.update(status='interrupted', reason=str(exc))
                self._save(batch)
                raise IntakeError(str(exc)) from exc
            try:
                used = sum(e.get('bytes', 0) for f in batch['files'] if f['index'] != index for e in f['entries'] if e['status'] == 'accepted')
                budget = self.max_staged - sum(f['size'] for f in batch['files'] if f['status'] != 'rejected' or 'original' in f) - used
                if original.suffix.lower() == '.zip':
                    self._extract(base, item, original, min(self.max_expanded, budget))
                else:
                    if item['size'] > budget:
                        raise IntakeError('Staging byte limit exceeded', 413)
                    audio_header(original)
                    self._require_space(item['size'])
                    target = base / 'audio' / f'{index:04d}' / original.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original, target)
                    item['entries'] = [{'name': original.name, 'status': 'accepted',
                                        'path': str(target.relative_to(base)), 'bytes': item['size'],
                                        'sha256': item['sha256'], 'source': item['original']}]
                item['status'] = 'accepted' if any(e['status'] == 'accepted' for e in item['entries']) else 'rejected'
                if item['status'] == 'rejected':
                    item['reason'] = 'No supported audio entries accepted; see entry report'
            except (IntakeError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError, ValueError, zlib.error, struct.error) as exc:
                self._discard_audio(base, item)
                for entry in item['entries']:
                    if entry['status'] == 'accepted':
                        entry.update(status='rejected', reason='Archive rolled back after validation failure')
                        entry.pop('path', None)
                    if entry['status'] == 'rejected' and 'reason' not in entry:
                        entry['reason'] = str(exc)
                item.update(status='rejected', reason=str(exc))
            self._save(batch)
            return self.receipt(batch_id)
        finally:
            self.lock.release()

    def _require_space(self, size):
        if shutil.disk_usage(self.root).free < size + 64 * 1024**2:
            raise IntakeError('Insufficient free disk space (64 MiB reserve required)', 507)

    @staticmethod
    def _hash(path):
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(CHUNK), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def _extract(self, base, item, original, budget):
        bounded_zip_directory(original, self.max_entries, self.max_directory)
        with zipfile.ZipFile(original) as archive:
            infos = archive.infolist()
            if len(infos) > self.max_entries:
                raise IntakeError('Too many ZIP entries', 413)
            total, unsafe = 0, False
            candidates = []
            for number, info in enumerate(infos):
                entry = {'name': info.orig_filename, 'zip_index': number, 'status': 'rejected'}
                item['entries'].append(entry)
                try:
                    name = safe_name(info.orig_filename)
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or (info.external_attr & 0x400):
                        raise IntakeError('Links and special ZIP entries are unsafe')
                    if info.flag_bits & 1:
                        raise IntakeError('Encrypted ZIP entries are unsupported')
                    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        raise IntakeError('Unsupported ZIP compression')
                except IntakeError as exc:
                    entry['reason'] = str(exc)
                    unsafe = True
                    continue
                if info.is_dir() or info.filename.startswith('__MACOSX/') or name.startswith('._') or name == '.DS_Store':
                    entry.update(status='skipped', reason='Directory or macOS metadata')
                    continue
                if Path(name).suffix.lower() not in AUDIO:
                    entry['reason'] = 'Unsupported entry type (nested ZIPs are not expanded)'
                    continue
                total += info.file_size
                if info.file_size > self.max_file or info.file_size / max(1, info.compress_size) > self.max_ratio:
                    entry['reason'] = 'ZIP member exceeds size or compression-ratio limit'
                    unsafe = True
                candidates.append((number, info, name, entry))
            if unsafe or total > budget:
                for entry in item['entries']:
                    if entry['status'] == 'rejected' and 'reason' not in entry:
                        entry['reason'] = 'Archive rejected before extraction'
                raise IntakeError('Unsafe ZIP entries or expanded/staging byte limit exceeded', 413 if total > budget else 400)
            self._require_space(total)
            extracted = 0
            for number, info, name, entry in candidates:
                # Numeric namespaces handle duplicate, casefolded and Unicode-equivalent
                # names identically on case-sensitive Linux and common Mac filesystems.
                name = unicodedata.normalize('NFC', name)
                target = base / 'audio' / f"{item['index']:04d}" / f'{number:04d}' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, count = hashlib.sha256(), 0
                with archive.open(info) as source, target.open('xb') as output:
                    while True:
                        chunk = source.read(CHUNK)
                        if not chunk:
                            break
                        count += len(chunk)
                        extracted += len(chunk)
                        if count > self.max_file or extracted > budget or count > info.file_size:
                            raise IntakeError('Expanded byte limit exceeded', 413)
                        output.write(chunk)
                        digest.update(chunk)
                audio_header(target)
                entry.update(status='accepted', path=str(target.relative_to(base)), bytes=count,
                             sha256=digest.hexdigest(), source=item['original'])
