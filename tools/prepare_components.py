#!/usr/bin/env python3
"""Export code-only handoffs. Runtime archives stay outside the public source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OMIT = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', 'build', 'dist', 'node_modules'}

def copy_code(source, target):
    for item in source.rglob('*'):
        rel = item.relative_to(source)
        if item.is_symlink() or not item.is_file() or any(part in OMIT or part.startswith('.') for part in rel.parts):
            continue
        if item.suffix in {'.pyc', '.log', '.pid', '.pem', '.key', '.ovpn', '.zip', '.whl'}:
            continue
        dest = target/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)
        dest.chmod(0o755 if item.suffix in {'.sh','.command'} else 0o644)

def prepare(handoff, vpn):
    dest = ROOT/'components'
    if any(dest.iterdir()):
        raise RuntimeError('components must be empty; export is intentionally explicit')
    for name in ('tspotify','ttelegram','tthings'):
        src = handoff/name
        if not (src/'app.json').is_file():
            raise RuntimeError(f'Missing handoff: {name}')
        copy_code(src/'source', dest/name/'source')
        for file in ('app.json', 'update.json', 'HANDOFF.md', 'install.py'):
            shutil.copy2(src/file, dest/name/file)
    # SoundCloud ships a small verified wheel and launch wrapper rather than an
    # install/update script; the suite owns its lifecycle and update channel.
    src = handoff/'tsoundcloud'
    if not (src/'app.json').is_file():
        raise RuntimeError('Missing handoff: tsoundcloud')
    target = dest/'tsoundcloud'
    copy_code(src/'source', target/'source')
    for file in ('app.json','HANDOFF.md','launch.py'):
        shutil.copy2(src/file,target/file)
    shutil.copytree(src/'runtime',target/'runtime')
    # TVPN code allowlist: mirrors the provided clean snapshot plus install/manage APIs.
    target = dest/'tvpn'/'source'
    for item in vpn.iterdir():
        if item.is_file() and (item.suffix in {'.py','.sh','.cmd','.ps1','.command','.json','.txt','.md'} or item.name in {'LICENSE','VERSION'}):
            if item.name.startswith('.'):
                continue
            target.mkdir(parents=True,exist_ok=True)
            shutil.copy2(item,target/item.name)
    for directory in ('platforms','bin'):
        copy_code(vpn/directory,target/directory)
    for name in ('riseup-ca.crt','LINUX-RUNTIME-NOTICES.md'):
        item=vpn/'assets'/name
        if item.is_file():
            (target/'assets').mkdir(exist_ok=True)
            shutil.copy2(item,target/'assets'/name)
    copy_code(vpn/'assets/licenses',target/'assets/licenses')
    metadata = {
        'tspotify':json.loads((dest/'tspotify/app.json').read_text())['version'],
        'tsoundcloud':json.loads((dest/'tsoundcloud/app.json').read_text())['version'],
        'ttelegram':(dest/'ttelegram/source/VERSION').read_text().strip(),
        'tthings':json.loads((dest/'tthings/app.json').read_text())['version'],
        'tvpn':(target/'VERSION').read_text().strip(),
    }
    actual = (dest/'tthings/source/tthings/__init__.py').read_text()
    if repr(metadata['tthings']) not in actual and '"'+metadata['tthings']+'"' not in actual:
        raise RuntimeError('tthings source version and handoff disagree')
    (dest/'versions.json').write_text(json.dumps(metadata,indent=2)+'\n')
    files={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.rglob('*')) if p.is_file()}
    (dest/'checksums.json').write_text(json.dumps(files,indent=2)+'\n')
    print(f'Exported {len(files)} code files: {metadata}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--handoff',required=True,type=Path);p.add_argument('--vpn',required=True,type=Path);a=p.parse_args();prepare(a.handoff,a.vpn)
