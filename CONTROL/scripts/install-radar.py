#!/usr/bin/env python3
"""Dry-run by default. Overlay only a verified Control baseline; never activate Radar."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile

BASELINE = 'b0c07b5cf1ca9bcb2a83fee2606f9e57698a64eac4ed0283f33123e8f75066ce'
SOURCE = Path(__file__).resolve().parents[1]
FILES = ('server.py', 'skill_radar.py')


def install(target, apply=False):
    target = Path(target).expanduser().resolve()
    server = target / 'server.py'
    if not server.is_file():
        raise ValueError('No installed server.py found. Identify the real JC owner first.')
    old_hash = hashlib.sha256(server.read_bytes()).hexdigest()
    new_hash = hashlib.sha256((SOURCE / 'server.py').read_bytes()).hexdigest()
    if old_hash not in (BASELINE, new_hash):
        raise ValueError('Unrecognised/custom JC server. Nothing changed. Adapt the small Radar route hook to that owner; do not replace the server or run the general installer.')
    bridge = target / 'skill_radar.py'
    if bridge.exists() and bridge.read_bytes() != (SOURCE / 'skill_radar.py').read_bytes():
        raise ValueError('Different Radar bridge already installed. Review its changes before replacing it.')
    if not apply:
        return 'Compatible baseline. Dry run only; no files changed, no collection enabled.'
    if target == SOURCE:
        return 'Already running from the reviewed checkout. No files changed, no collection enabled.'
    backup_root = target / '.radar-backups'
    backup_root.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='before-radar-', dir=backup_root))
    existing = set()
    for name in FILES:
        if (target / name).exists():
            shutil.copy2(target / name, backup / name)
            existing.add(name)
    try:
        for name in FILES:
            staged = target / ('.radar-stage-' + name)
            shutil.copy2(SOURCE / name, staged)
            staged.replace(target / name)
    except Exception:
        for name in FILES:
            if name in existing:
                shutil.copy2(backup / name, target / name)
            elif (target / name).exists():
                (target / name).unlink()
        raise
    finally:
        for name in FILES:
            staged = target / ('.radar-stage-' + name)
            if staged.exists(): staged.unlink()
    return f'Installed two reviewed files. Backup: {backup}. Restart the identified JC owner when ready. Radar remains disabled unless explicitly configured.'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try: print(install(args.target,args.apply))
    except (OSError,ValueError) as exc: parser.exit(1,str(exc)+'\n')
