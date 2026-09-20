"""Rebuild the pinned JC distribution from the canonical authored assets."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import json

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
entries = {}
for name in ['app.js', 'index.html', 'intake.js', 'sample.js', 'site-tools.js', 'speech.js', 'style.css', 'voices.js']:
    entries[f'reader/{name}'] = (dist / name).read_bytes()
for name in ['reader-client.js', 'module.json', 'JUICE_READER_Install_in_JC.md']:
    entries[f'integration/{name}'] = (dist / 'integration' / name).read_bytes()
source = {
    'release': 'reader-integration-2',
    'canonical_url': 'https://juice-reader.xntfsstt5z.chatgpt.site',
    'installation_status': 'prepared; not installed on the Mac',
    'chatgpt_connection': 'site tools implemented; user desktop connection required',
    'native_mobile_chatgpt_stream': 'not connected',
    'files': {name: sha256(data).hexdigest() for name, data in entries.items()},
}
entries['SOURCE.json'] = (json.dumps(source, indent=2) + '\n').encode()
entries['SHA256SUMS'] = ''.join(f'{sha256(data).hexdigest()}  {name}\n' for name, data in sorted(entries.items())).encode()
target = dist / 'integration' / 'juice-reader-jc-kit.zip'
with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
    for name, data in sorted(entries.items()):
        info = ZipInfo(name, (2026, 9, 9, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, data)
print(f'Updated {target.name}: {len(entries)} files')
