"""Fetch the immutable author-supplied Windows payload; verify before extraction."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ttools.distribution import digest, extract_zip
ROOT=Path(__file__).resolve().parents[1]
REVIEWED_OVERRIDES=(
    'source/windows_bootstrap.py',
    'manage.py',
    'source/composer.py',
    'source/engine.py',
    'source/media.py',
    'source/chat_transition.py',
    'source/render_layout.py',
    'source/settings.py',
    'source/ui.py',
    'source/demo_scenario.py',
    'tests/smoke_ui_pty.py',
    'tests/test_core.py',
    'tests/artifacts/chat-list.png',
    'tests/artifacts/conversation.png',
    'tests/artifacts/chat-transition.gif',
)
def main():
    spec=json.loads((ROOT/'components/ttelegram/windows-native-package.json').read_text())
    destination=ROOT/'components/ttelegram/runtime/windows-native'
    if destination.exists():
        raise RuntimeError('Destination already exists; remove it explicitly before downloading again')
    with tempfile.TemporaryDirectory() as temporary:
        archive=Path(temporary)/'payload.zip'
        urllib.request.urlretrieve(spec['url'],archive)
        if digest(archive)!=spec['sha256']:raise RuntimeError('Windows Telegram archive SHA-256 mismatch')
        extracted=Path(temporary)/"extracted"
        extract_zip(archive,extracted)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(extracted/"ttelegram-windows-native"),destination)
    # Author inventory covers runtime, dependencies and integration code.
    inventory=json.loads((destination/'files.json').read_text())
    for name,expected in inventory.items():
        path=(destination/name).resolve()
        if not path.is_relative_to(destination.resolve()) or digest(path)!=expected:
            raise RuntimeError('Windows Telegram inventory mismatch: '+name)
    apply_integration_fixes(destination,inventory)

def apply_integration_fixes(destination,inventory):
    # Apply the reviewed UI and integration sources after verifying the immutable author archive.
    overrides=ROOT/'components/ttelegram/windows-native'
    checksums_path=destination/'SHA256SUMS.txt'
    checksum_order=[]
    checksums={}
    for line in checksums_path.read_text().splitlines():
        expected,separator,name=line.partition('  ')
        if not separator or not name or name in checksums:
            raise RuntimeError('Invalid Windows Telegram SHA256SUMS.txt entry: '+line)
        checksum_order.append(name)
        checksums[name]=expected
    if set(inventory)!=set(checksums):
        raise RuntimeError('Windows Telegram files.json and SHA256SUMS.txt inventories differ')
    if any(inventory[name]!=checksums[name] for name in inventory):
        raise RuntimeError('Windows Telegram files.json and SHA256SUMS.txt hashes differ')
    for name in REVIEWED_OVERRIDES:
        source=overrides/name
        if not source.is_file():
            raise RuntimeError('Missing reviewed Windows Telegram override: '+name)
        if name not in inventory:
            checksum_order.append(name)
            inventory[name]=None
            checksums[name]=None
    for name in REVIEWED_OVERRIDES:
        source=overrides/name
        target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        inventory[name]=digest(destination/name)
        checksums[name]=inventory[name]
    if any(inventory[name]!=checksums[name] for name in inventory):
        raise RuntimeError('Integrated Windows Telegram inventories disagree')
    for name,expected in inventory.items():
        path=(destination/name).resolve()
        if not path.is_relative_to(destination.resolve()) or not path.is_file() or digest(path)!=expected:
            raise RuntimeError('Integrated Windows Telegram inventory mismatch: '+name)
    (destination/'files.json').write_text(json.dumps(inventory,indent=2)+'\n')
    checksums_path.write_text('\n'.join(f'{checksums[name]}  {name}' for name in checksum_order)+'\n')
if __name__=='__main__':main()
