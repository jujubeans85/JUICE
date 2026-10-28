import io
import fcntl
import os
import random
import subprocess
import json
import socket
import stat
import struct
import sys
import tempfile
import threading
import unittest
import warnings
import wave
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_intake import CHUNK, IntakeError, IntakeStore
import server


def wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x01\x00' * 80)
    return output.getvalue()


def bundle(entries, compression=zipfile.ZIP_STORED):
    data = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(data, 'w', compression=compression) as archive:
            for name, content in entries:
                archive.writestr(name, content)
    return data.getvalue()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'intake'
        self.store = IntakeStore(self.root)

    def import_one(self, name, data, store=None):
        store = store or self.store
        batch = store.create([{'name': name, 'size': len(data)}])
        return store.upload(batch['id'], 0, io.BytesIO(data), len(data))

    def test_normal_audio_and_original_hash(self):
        data = wav()
        batch = self.import_one('kick.wav', data)
        item = batch['files'][0]
        self.assertEqual(item['status'], 'accepted')
        base = self.root / batch['id']
        self.assertEqual((base / item['original']).read_bytes(), data)
        self.assertEqual((base / item['entries'][0]['path']).read_bytes(), data)
        self.assertEqual(item['sha256'], item['entries'][0]['sha256'])
        self.assertEqual((base / item['original']).stat().st_mode & 0o222, 0)
        self.assertEqual(batch['processing'], 'not connected')
        self.assertTrue(json.loads((base / 'manifest.json').read_text())['ready'])

    def test_wav_aiff_aif_and_mp3_headers(self):
        for name, data in [('audio.WAV', wav()), ('audio.aiff', b'FORM\x00\x00\x00\x04AIFF'),
                           ('audio.aif', b'FORM\x00\x00\x00\x04AIFC'), ('audio.mp3', b'ID3\x04\x00\x00\x00\x00\x00\x00')]:
            with self.subTest(name=name):
                self.assertEqual(self.import_one(name, data)['files'][0]['status'], 'accepted')

    def test_multiple_stems_and_duplicate_loose_names(self):
        data = wav()
        batch = self.store.create([{'name': 'stem.wav', 'size': len(data)}] * 3)
        for index in range(3):
            batch = self.store.upload(batch['id'], index, io.BytesIO(data), len(data))
        self.assertTrue(batch['ready'])
        self.assertEqual([f['status'] for f in batch['files']], ['accepted'] * 3)
        self.assertEqual(len({f['original'] for f in batch['files']}), 3)

    def test_zip_nested_stems_duplicates_case_and_unicode(self):
        names = ['drums/kick.wav', 'bass.wav', 'bass.wav', 'BASS.wav', 'café.wav', 'cafe\u0301.wav']
        data = bundle([(name, wav()) for name in names])
        batch = self.import_one('stems.zip', data)
        item = batch['files'][0]
        self.assertEqual(item['status'], 'accepted')
        self.assertEqual([e['name'] for e in item['entries']], names)
        self.assertEqual(len({e['path'] for e in item['entries']}), 6)
        for entry in item['entries']:
            self.assertEqual((self.root / batch['id'] / entry['path']).read_bytes(), wav())

    def test_mixed_zip_reports_every_entry(self):
        data = bundle([('kick.wav', wav()), ('notes.txt', b'note'), ('__MACOSX/._kick.wav', b'junk'),
                       ('stems/', b''), ('inner.zip', b'not recursively extracted')])
        item = self.import_one('mix.zip', data)['files'][0]
        self.assertEqual([e['status'] for e in item['entries']], ['accepted', 'rejected', 'skipped', 'skipped', 'rejected'])

    def test_rejected_selection_reports_all_files(self):
        batch = self.store.create([{'name': '../escape.wav', 'size': 1}, {'name': 'document.pdf', 'size': 1},
                                   {'name': 'empty.wav', 'size': 0}, {'name': 'good.wav', 'size': len(wav())}])
        self.assertEqual([f['status'] for f in batch['files']], ['rejected'] * 3 + ['pending'])
        self.assertTrue(all(f['reason'] for f in batch['files'][:3]))

    def test_bad_audio_header_preserves_original(self):
        batch = self.import_one('fake.wav', b'not an audio file')
        item = batch['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertTrue((self.root / batch['id'] / item['original']).exists())

    def test_seeded_corrupt_zip_mutations_produce_terminal_receipts(self):
        data = bundle([('stem.wav', wav())], zipfile.ZIP_DEFLATED)
        rng = random.Random(20261028)
        for index in range(100):
            broken = bytearray(data)
            for _ in range(rng.randint(1, 5)):
                broken[rng.randrange(len(broken))] = rng.randrange(256)
            batch = self.import_one('mutation.zip', bytes(broken))
            self.assertIn(batch['files'][0]['status'], {'accepted', 'rejected'}, index)

    def test_corrupt_archive_preserves_original(self):
        batch = self.import_one('broken.zip', b'PK\x03\x04corrupt')
        item = batch['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertIn('Corrupt', item['reason'])
        self.assertEqual((self.root / batch['id'] / item['original']).read_bytes(), b'PK\x03\x04corrupt')

    def test_crc_failure_rolls_back_all_members(self):
        data = bundle([('good.wav', wav()), ('bad.wav', wav())])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.infolist()[1]
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        broken = bytearray(data)
        broken[offset + 50] ^= 0xff
        batch = self.import_one('crc.zip', bytes(broken))
        item = batch['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertFalse(any(e['status'] == 'accepted' for e in item['entries']))
        self.assertFalse((self.root / batch['id'] / 'audio' / '0000').exists())

    def test_unsafe_paths_reject_entire_archive(self):
        names = ['../escape.wav', '/tmp/escape.wav', 'C:/escape.wav', 'dir\\escape.wav',
                 'a/../../escape.wav', 'a//escape.wav', 'bad./escape.wav', 'bad\n.wav']
        for name in names:
            with self.subTest(name=name):
                batch = self.import_one('unsafe.zip', bundle([('good.wav', wav()), (name, wav())]))
                item = batch['files'][0]
                self.assertEqual(item['status'], 'rejected')
                self.assertEqual(len(item['entries']), 2)
                self.assertFalse((self.root / batch['id'] / 'audio').exists())
                self.assertTrue(all(e.get('reason') for e in item['entries']))
        self.assertFalse((self.root.parent / 'escape.wav').exists())

    def test_invalid_utf8_zip_filename_is_rejected_not_left_receiving(self):
        data = bytearray(bundle([('x.wav', wav())]))
        central = data.index(b'PK\x01\x02')
        struct.pack_into('<H', data, 6, 0x800)
        struct.pack_into('<H', data, central + 8, 0x800)
        data[30] = 255
        data[central + 46] = 255
        item = self.import_one('invalid-name.zip', bytes(data))['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertIn('decode', item['reason'])

    def test_encrypted_archive_is_explicitly_rejected(self):
        data = bytearray(bundle([('a.wav', wav())]))
        central = data.index(b'PK\x01\x02')
        struct.pack_into('<H', data, 6, 1)
        struct.pack_into('<H', data, central + 8, 1)
        item = self.import_one('encrypted.zip', bytes(data))['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertIn('Encrypted', item['entries'][0]['reason'])

    def test_nul_in_zip_filename_rejected(self):
        data = bundle([('badX.wav', wav())]).replace(b'badX.wav', b'bad\x00.wav')
        item = self.import_one('nul.zip', data)['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertIn('Unsafe', item['entries'][0]['reason'])

    def test_symlink_and_special_files_rejected(self):
        for mode in [stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600, stat.S_IFCHR | 0o600]:
            info = zipfile.ZipInfo('unsafe.wav')
            info.create_system = 3
            info.external_attr = mode << 16
            item = self.import_one('link.zip', bundle([(info, wav())]))['files'][0]
            self.assertEqual(item['status'], 'rejected')
            self.assertIn('special', item['entries'][0]['reason'])

    def test_size_and_expansion_limits(self):
        store = IntakeStore(self.root, max_file=500, max_batch=600, max_expanded=100)
        batch = store.create([{'name': 'large.zip', 'size': 501}])
        self.assertEqual(batch['files'][0]['status'], 'rejected')
        with self.assertRaisesRegex(IntakeError, 'batch'):
            store.create([{'name': 'a.wav', 'size': 400}, {'name': 'b.wav', 'size': 400}])
        data = bundle([('kick.wav', wav())])
        self.assertEqual(self.import_one('big.zip', data, store)['files'][0]['status'], 'rejected')

    def test_staging_budget_across_multiple_archives(self):
        data = bundle([('kick.wav', wav())])
        store = IntakeStore(self.root, max_staged=len(data) * 2 + len(wav()) + 1)
        batch = store.create([{'name': 'a.zip', 'size': len(data)}, {'name': 'b.zip', 'size': len(data)}])
        store.upload(batch['id'], 0, io.BytesIO(data), len(data))
        batch = store.upload(batch['id'], 1, io.BytesIO(data), len(data))
        self.assertEqual([f['status'] for f in batch['files']], ['accepted', 'rejected'])

    def test_bomb_ratio_and_member_limit(self):
        data = bundle([('big.wav', wav() + b'\0' * 10000)], zipfile.ZIP_DEFLATED)
        store = IntakeStore(self.root, max_ratio=2)
        self.assertEqual(self.import_one('bomb.zip', data, store)['files'][0]['status'], 'rejected')
        store = IntakeStore(self.root, max_entries=1)
        data = bundle([('a.wav', wav()), ('b.wav', wav())])
        self.assertEqual(self.import_one('many.zip', data, store)['files'][0]['status'], 'rejected')
        store = IntakeStore(self.root, max_directory=10)
        self.assertEqual(self.import_one('directory.zip', data, store)['files'][0]['status'], 'rejected')

    def test_zip64_members_work(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            with archive.open('stem.wav', 'w', force_zip64=True) as source:
                source.write(wav())
        self.assertEqual(self.import_one('zip64.zip', data.getvalue())['files'][0]['status'], 'accepted')

    def test_zip64_end_record(self):
        data = bundle([('stem.wav', wav())])
        position = data.rfind(b'PK\x05\x06')
        values = list(struct.unpack('<4s4H2LH', data[position:]))
        count, size, offset = values[4], values[5], values[6]
        record = struct.pack('<4sQ2H2L4Q', b'PK\x06\x06', 44, 45, 45, 0, 0, count, count, size, offset)
        locator = struct.pack('<4sLQL', b'PK\x06\x07', 0, position, 1)
        values[3:7] = [65535, 65535, 0xffffffff, 0xffffffff]
        zip64 = data[:position] + record + locator + struct.pack('<4s4H2LH', *values)
        self.assertEqual(self.import_one('zip64-end.zip', zip64)['files'][0]['status'], 'accepted')

    def test_rejected_originals_still_count_toward_staging_budget(self):
        data = bundle([('stem.wav', wav())])
        invalid = b'bad ZIP data'
        store = IntakeStore(self.root, max_staged=len(data) + len(invalid) + len(wav()) - 1)
        batch = store.create([{'name': 'bad.zip', 'size': len(invalid)}, {'name': 'good.zip', 'size': len(data)}])
        store.upload(batch['id'], 0, io.BytesIO(invalid), len(invalid))
        batch = store.upload(batch['id'], 1, io.BytesIO(data), len(data))
        self.assertEqual([f['status'] for f in batch['files']], ['rejected', 'rejected'])
        self.assertFalse(batch['ready'])

    def test_interruption_from_read_timeout(self):
        class Timeout(io.BytesIO):
            def read(self, amount=-1):
                raise TimeoutError('stalled sender')
        batch = self.store.create([{'name': 'stem.wav', 'size': len(wav())}])
        with self.assertRaisesRegex(IntakeError, 'stalled'):
            self.store.upload(batch['id'], 0, Timeout(), len(wav()))
        self.assertEqual(self.store.receipt(batch['id'])['files'][0]['status'], 'interrupted')
        self.assertFalse(list((self.root / batch['id']).rglob('*.part')))

    def test_interrupted_upload_can_retry_without_partial_publish(self):
        data = wav()
        batch = self.store.create([{'name': 'kick.wav', 'size': len(data)}])
        with self.assertRaisesRegex(IntakeError, 'Interrupted'):
            self.store.upload(batch['id'], 0, io.BytesIO(data[:20]), len(data))
        receipt = self.store.receipt(batch['id'])
        self.assertEqual(receipt['files'][0]['status'], 'interrupted')
        self.assertFalse(list((self.root / batch['id']).rglob('*.part')))
        self.assertFalse(list((self.root / batch['id']).rglob('kick.wav')))
        receipt = self.store.upload(batch['id'], 0, io.BytesIO(data), len(data))
        self.assertEqual(receipt['files'][0]['status'], 'accepted')

    def test_restart_recovers_interruption_preserving_complete_original(self):
        data = wav()
        batch = self.store.create([{'name': 'kick.wav', 'size': len(data)}])
        base = self.root / batch['id']
        dest = base / 'originals' / '0000'
        dest.mkdir(parents=True)
        (dest / 'kick.wav').write_bytes(data)
        (dest / 'upload.part').write_bytes(b'partial')
        (base / 'audio' / '0000').mkdir(parents=True)
        (base / 'audio' / '0000' / 'incomplete.wav').write_bytes(b'partial')
        batch['files'][0]['status'] = 'receiving'
        self.store._save(batch)
        restored = IntakeStore(self.root)
        self.assertEqual(restored.receipt(batch['id'])['files'][0]['status'], 'interrupted')
        self.assertFalse((dest / 'upload.part').exists())
        self.assertFalse((base / 'audio' / '0000').exists())
        self.assertEqual((dest / 'kick.wav').read_bytes(), data)
        receipt = restored.upload(batch['id'], 0, io.BytesIO(data), len(data))
        self.assertEqual(receipt['files'][0]['status'], 'accepted')

    def test_retry_cannot_overwrite_a_preserved_original(self):
        data = wav()
        batch = self.store.create([{'name': 'kick.wav', 'size': len(data)}])
        dest = self.root / batch['id'] / 'originals' / '0000'
        dest.mkdir(parents=True)
        (dest / 'kick.wav').write_bytes(b'X' * len(data))
        with self.assertRaisesRegex(IntakeError, 'differs'):
            self.store.upload(batch['id'], 0, io.BytesIO(data), len(data))
        self.assertEqual((dest / 'kick.wav').read_bytes(), b'X' * len(data))

    def test_bounded_reads_and_no_overwrite_on_repeat(self):
        data = wav() + b'\0' * (CHUNK * 2)
        class Bounded(io.BytesIO):
            def read(self, amount=-1):
                if not 0 < amount <= CHUNK:
                    raise AssertionError('Unbounded upload read')
                return super().read(amount)
        batch = self.store.create([{'name': 'long.wav', 'size': len(data)}])
        self.store.upload(batch['id'], 0, Bounded(data), len(data))
        with self.assertRaisesRegex(IntakeError, 'completed'):
            self.store.upload(batch['id'], 0, Bounded(data), len(data))

    def test_disk_space_rejected_before_read(self):
        batch = self.store.create([{'name': 'kick.wav', 'size': len(wav())}])
        with patch('audio_intake.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            with self.assertRaisesRegex(IntakeError, 'disk space'):
                self.store.upload(batch['id'], 0, io.BytesIO(wav()), len(wav()))
        self.assertEqual(self.store.receipt(batch['id'])['files'][0]['status'], 'pending')

    def test_directory_count_mismatch_rejected_before_zipfile_allocation(self):
        data = bytearray(bundle([('a.wav', wav()), ('b.wav', wav())]))
        pos = data.rfind(b'PK\x05\x06')
        struct.pack_into('<HH', data, pos + 8, 1, 1)
        item = self.import_one('counts.zip', bytes(data))['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertIn('count mismatch', item['reason'])

    def test_corrupt_deflate_stream_is_reported(self):
        data = bytearray(bundle([('a.wav', wav())], zipfile.ZIP_DEFLATED))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.infolist()[0]
            start = info.header_offset + 30 + len(info.filename)
        data[start:start+4] = b'\xff' * 4
        item = self.import_one('deflate.zip', bytes(data))['files'][0]
        self.assertEqual(item['status'], 'rejected')
        self.assertTrue(item['entries'][0]['reason'])

    def test_length_and_concurrency_rejected_before_read(self):
        batch = self.store.create([{'name': 'kick.wav', 'size': len(wav())}])
        with self.assertRaisesRegex(IntakeError, 'Content-Length'):
            self.store.upload(batch['id'], 0, io.BytesIO(wav()), 3)
        with self.store.lock:
            with self.assertRaisesRegex(IntakeError, 'active'):
                self.store.upload(batch['id'], 0, io.BytesIO(wav()), len(wav()))


class StartupTests(unittest.TestCase):
    def test_old_listener_is_not_reused_or_recovered(self):
        with patch.object(server, 'already_running', return_value=True), patch.object(server, 'urlopen') as request, patch.object(server, 'intake_store') as store, patch.object(server.webbrowser, 'open') as browser:
            request.return_value.__enter__.return_value.read.return_value = b'{"version":"old"}'
            self.assertEqual(server.main(), 2)
            store.assert_not_called()
            browser.assert_not_called()

    def test_matching_listener_reuses_without_recovery(self):
        with patch.object(server, 'already_running', return_value=True), patch.object(server, 'urlopen') as request, patch.object(server, 'intake_store') as store, patch.object(server.webbrowser, 'open') as browser:
            request.return_value.__enter__.return_value.read.return_value = json.dumps({'app': server.APP_NAME, 'version': server.APP_VERSION}).encode()
            self.assertEqual(server.main(), 0)
            store.assert_not_called()
            browser.assert_called_once()

    def test_existing_intake_owner_prevents_cross_port_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'CAPTURE' / 'audio-intake'
            root.mkdir(parents=True)
            with (root / '.owner.lock').open('a') as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(server, 'DATA_ROOT', Path(directory)), patch.object(server, 'already_running', return_value=False), patch.object(server, 'ensure_layout'), patch.object(server, 'intake_store') as store:
                    self.assertEqual(server.main(), 2)
                    store.assert_not_called()

    def test_nonlocal_binding_is_refused(self):
        with patch.object(server, 'HOST', '0.0.0.0'):
            self.assertEqual(server.main(), 2)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.target = self.home / 'JUICE' / 'CONTROL'
        self.source = Path(__file__).resolve().parents[1]
        self.env = dict(os.environ, HOME=str(self.home), JUICE_CONTROL_INSTALL_DIR=str(self.target), JUICE_DATA_ROOT=str(self.home / 'data'))

    def install(self):
        return subprocess.run(['bash', str(self.source / 'scripts' / 'install.sh')], env=self.env, capture_output=True, text=True)

    def test_divergent_live_server_is_untouched(self):
        self.target.mkdir(parents=True)
        live = self.target / 'server.py'
        live.write_text('# existing 8780 capture owner')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('target server differs', result.stderr)
        self.assertEqual(live.read_text(), '# existing 8780 capture owner')
        self.assertFalse((self.target / 'audio_intake.py').exists())
        self.assertFalse((self.home / 'JUICE' / 'CONTROL.backups').exists())

    def test_matching_install_backs_up_and_preserves_local_modules(self):
        self.target.mkdir(parents=True)
        (self.target / 'server.py').write_bytes((self.source / 'server.py').read_bytes())
        (self.target / 'local-module.py').write_text('preserve me')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / 'local-module.py').read_text(), 'preserve me')
        self.assertEqual((self.target / 'audio_intake.py').read_bytes(), (self.source / 'audio_intake.py').read_bytes())
        backups = list((self.home / 'JUICE' / 'CONTROL.backups').glob('CONTROL.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'local-module.py').read_text(), 'preserve me')
        self.assertTrue((self.home / 'data' / 'CAPTURE').is_dir())

    def test_fresh_install(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / 'intake.html').exists())
        self.assertTrue(os.access(self.target / 'scripts' / 'identify-jc.sh', os.X_OK))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_store = server.INTAKE
        server.INTAKE = IntakeStore(Path(cls.temp.name) / 'intake', max_file=1024)
        cls.logs = patch.object(server.Handler, 'log_message')
        cls.logs.start()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_port

    @classmethod
    def tearDownClass(cls):
        cls.logs.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        server.INTAKE = cls.original_store
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=3)
        self.addCleanup(connection.close)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, response.read()

    def create(self):
        code, data = self.request('POST', '/api/intake/batches', json.dumps({'files': [{'name': 'a.wav', 'size': len(wav())}]}),
                                  {'X-Juice-Token': server.CSRF_TOKEN, 'Content-Type': 'application/json'})
        self.assertEqual(code, 201)
        return json.loads(data)

    def test_http_import_and_receipt(self):
        batch = self.create()
        code, data = self.request('POST', f"/api/intake/batches/{batch['id']}/files/0", wav(), {'X-Juice-Token': server.CSRF_TOKEN})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(data)['files'][0]['status'], 'accepted')
        code, data = self.request('GET', f"/api/intake/batches/{batch['id']}")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(data)['files'][0]['status'], 'accepted')

    def test_disconnect_over_real_socket(self):
        batch = self.create()
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        payload = (f"POST /api/intake/batches/{batch['id']}/files/0 HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                   f"X-Juice-Token: {server.CSRF_TOKEN}\r\nContent-Length: {len(wav())}\r\n\r\n").encode() + wav()[:10]
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        # Drain response: guarantees handler recorded the disconnection before checking.
        while sock.recv(4096):
            pass
        sock.close()
        code, data = self.request('GET', f"/api/intake/batches/{batch['id']}")
        self.assertEqual(json.loads(data)['files'][0]['status'], 'interrupted')
        code, data = self.request('POST', f"/api/intake/batches/{batch['id']}/files/0", wav(), {'X-Juice-Token': server.CSRF_TOKEN})
        self.assertEqual(json.loads(data)['files'][0]['status'], 'accepted')

    def test_csrf_origin_and_dns_rebinding(self):
        for headers in [{}, {'X-Juice-Token': server.CSRF_TOKEN, 'Origin': 'https://evil.invalid'},
                        {'X-Juice-Token': server.CSRF_TOKEN, 'Host': 'evil.invalid'},
                        {'X-Juice-Token': server.CSRF_TOKEN, 'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.request('POST', '/api/intake/batches', b'{}', headers)[0], 403)
        self.assertEqual(self.request('GET', '/api/intake', headers={'Host': 'evil.invalid'})[0], 403)

    def test_invalid_lengths_types_routes_and_size(self):
        for body, headers, expected in [(b'{}', {'Content-Length': '-1'}, 411),
                                        (b'{}', {'Content-Length': '65537'}, 413),
                                        (b'{}', {'Transfer-Encoding': 'chunked'}, 411),
                                        (b'[]', {'Content-Type': 'application/json'}, 400),
                                        (b'no JSON', {'Content-Type': 'application/json'}, 400)]:
            headers['X-Juice-Token'] = server.CSRF_TOKEN
            self.assertEqual(self.request('POST', '/api/intake/batches', body, headers)[0], expected)
        batch = self.create()
        code, _ = self.request('POST', f"/api/intake/batches/{batch['id']}/files/0", b'X' * 1025, {'X-Juice-Token': server.CSRF_TOKEN})
        self.assertEqual(code, 413)
        self.assertEqual(self.request('GET', '/api/intake/batches/' + '0'*32)[0], 404)
        self.assertEqual(self.request('POST', '/unknown', b'')[0], 404)

    def test_existing_page_health_diagnostics_and_zed_actions(self):
        with patch.object(server, 'zed_status', return_value={'available': True, 'command': 'mock-zed', 'error': None}):
            code, page = self.request('GET', '/')
            self.assertEqual(code, 200)
            self.assertIn(b'name="csrf"', page)
            self.assertIn(b'id="audio-intake"', page)
            self.assertIn(b'Crate Map', page)
            self.assertEqual(self.request('GET', '/health')[0], 200)
            code, diagnostics = self.request('GET', '/api/diagnostics')
            self.assertIn('audio_intake', json.loads(diagnostics))
            for target in ['control', 'creative', 'build_repos', 'capture']:
                with self.subTest(target=target), patch.object(server, 'open_in_zed', return_value=(True, 'Opened in Zed')) as opener, patch.object(server.Path, 'mkdir'):
                    code, _ = self.request('POST', '/open', urlencode({'target': target, 'csrf': server.CSRF_TOKEN}))
                    self.assertEqual(code, 200)
                    opener.assert_called_once_with(server.safe_target(target))
            self.assertEqual(self.request('POST', '/open', urlencode({'target': 'escape', 'csrf': server.CSRF_TOKEN}))[0], 400)
            self.assertEqual(self.request('POST', '/open', urlencode({'target': 'capture'}))[0], 403)
        code, js = self.request('GET', '/intake.js')
        self.assertEqual(code, 200)
        self.assertIn(b'xhr.send(file)', js)


if __name__ == '__main__':
    unittest.main()
