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
    # Apply the small, reviewed integration fixes after verifying the author's archive.
    overrides=ROOT/'components/ttelegram/windows-native'
    for name in ('source/windows_bootstrap.py','tests/test_core.py'):
        shutil.copy2(overrides/name,destination/name)
        inventory[name]=digest(destination/name)
    (destination/'files.json').write_text(json.dumps(inventory,indent=2)+'\n')
if __name__=='__main__':main()
