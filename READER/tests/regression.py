"""Offline source gate. No live Site, speech provider, or Mac connection needed."""
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script':
            assert attrs.get('src'), 'Inline scripts need explicit review'
            self.refs.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.refs.append(attrs['href'])


def source_checks():
    for file in sorted(DIST.rglob('*.js')):
        run('node', '--check', str(file))
    for file in sorted(ROOT.rglob('*.json')):
        json.loads(file.read_text())
    page = Assets()
    page.feed((DIST / 'index.html').read_text())
    assert len(page.ids) == len(set(page.ids)), 'Duplicate HTML IDs'
    assert 'app.js' in page.refs and 'speech.js' in page.refs
    for ref in page.refs:
        assert not ref.startswith('/') and ':' not in ref and '..' not in PurePosixPath(ref).parts, ref
        assert (DIST / ref).is_file(), f'Missing asset: {ref}'
    # Explicit public fixture allowlist: do not copy the private Site prompt here.
    assert (DIST / 'sample.js').read_text().strip() == 'window.JUICE_REPAIR_TEXT = "Paste something you want to hear, then press Read aloud.";', 'Public neutral sample changed; review privacy boundary'
    assert not (ROOT / '.openai').exists(), 'Site-specific hosting metadata belongs outside public Reader source'
    module = json.loads((DIST / 'integration/module.json').read_text())
    assert module['url'] == '/reader/'
    assert module['auto_load'] == dict(enabled=True, minimum_paragraphs=3, role='assistant', status='completed', autoplay=False)


def expected_files():
    names = ['app.js', 'index.html', 'intake.js', 'sample.js', 'site-tools.js', 'speech.js', 'style.css', 'voices.js']
    expected = {f'reader/{name}': (DIST / name).read_bytes() for name in names}
    for name in ['reader-client.js', 'module.json', 'JUICE_READER_Install_in_JC.md']:
        expected[f'integration/{name}'] = (DIST / 'integration' / name).read_bytes()
    return expected


def check_kit(archive_path):
    expected = expected_files()
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entries'
        assert set(names) == set(expected) | {'SOURCE.json', 'SHA256SUMS'}, 'Unexpected/missing ZIP entry'
        assert archive.testzip() is None, 'ZIP CRC failure'
        for name, data in expected.items():
            assert archive.read(name) == data, f'Stale kit member: {name}'
        source = json.loads(archive.read('SOURCE.json'))
        assert source['files'] == {n: sha256(b).hexdigest() for n, b in expected.items()}, 'Source manifest mismatch'
        assert source['installation_status'] == 'prepared; not installed on the Mac'
        assert source['native_mobile_chatgpt_stream'] == 'not connected'
        expected['SOURCE.json'] = archive.read('SOURCE.json')
        checksums = ''.join(f'{sha256(data).hexdigest()}  {name}\n' for name, data in sorted(expected.items()))
        assert archive.read('SHA256SUMS') == checksums.encode(), 'Checksum manifest mismatch'
        return {name: archive.read(name) for name in names}


def main():
    source_checks()
    run('node', 'tests/site-tools.cjs')
    run('node', '--test', 'tests/reader.cjs')
    relative = Path('dist/integration/juice-reader-jc-kit.zip')
    committed = check_kit(ROOT / relative)  # Check BEFORE rebuilding.
    with TemporaryDirectory() as temp:
        copy = Path(temp) / 'reader'
        shutil.copytree(ROOT, copy)
        subprocess.run([sys.executable, str(copy / 'scripts/package-jc-kit.py')], check=True)
        rebuilt = check_kit(copy / relative)
        # Compare uncompressed contents; zlib output can differ by platform/version.
        assert rebuilt == committed, 'Rebuild differs from committed distribution'
    print('PASS: Reader syntax, assets, neutral fixture, behavior, kit membership, hashes and rebuild parity.')
    print('Separate/unverified: physical-device audio, live desktop contact, Mac installation. No deployment performed.')


if __name__ == '__main__':
    main()
