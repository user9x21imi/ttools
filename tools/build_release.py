#!/usr/bin/env python3
"""Produce platform-labeled ZIPs, complete inventories and the update feed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ttools import __version__
from ttools.distribution import digest,verify_bundle

PLATFORMS=('linux-x86_64','macos-arm64','macos-x86_64','windows-x86_64')
EXCLUDE={'__pycache__','.git','.venv','.pytest_cache','build','dist'}

def copy_tree(source,target):
    for path in source.rglob('*'):
        rel=path.relative_to(source)
        if not path.is_file() or path.is_symlink() or any(x in EXCLUDE for x in rel.parts) or path.suffix=='.pyc':continue
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)

def build(output,platforms=PLATFORMS,handoff=None):
    output.mkdir(parents=True,exist_ok=True)
    artifacts=[]
    for target_platform in platforms:
        with tempfile.TemporaryDirectory(prefix='ttools-package-') as temporary:
            root=Path(temporary)/'ttools';root.mkdir()
            for directory in ('ttools','components','konsole','scripts'):
                copy_tree(ROOT/directory,root/directory)
            for name in ('installer.py','bootstrap.py','install-local.py','README.md','LICENSE','THIRD_PARTY.md','icon.svg','logo.svg'):
                shutil.copy2(ROOT/name,root/name)
            copy_tree(ROOT/'docs',root/'docs')
            launcher='Install-ttools.sh' if target_platform.startswith('linux') else 'Install-ttools.command' if target_platform.startswith('macos') else 'Install-ttools.cmd'
            shutil.copy2(ROOT/'scripts'/launcher,root/launcher)
            if target_platform=='linux-x86_64':
                if handoff:
                    # Author-prepared packages; source only on other operating systems.
                    for app,folders in [('tspotify',['runtime']),('ttelegram',['wheels'])]:
                        for folder in folders:
                            copy_tree(handoff/app/folder,root/'components'/app/folder)
                else:
                    wheels=ROOT/'components/ttelegram/wheels'
                    if not wheels.is_dir() or not any(wheels.glob('*.whl')):
                        raise RuntimeError('Linux release requires the Telegram wheelhouse. Run tools/download_wheels.py or pass --handoff.')
                # Telegram's original installer verifies its own file inventory.
                component=root/'components/ttelegram'
                files=[p for p in component.rglob('*') if p.is_file() and p.relative_to(component).parts[0] in ('source','wheels')]
                (component/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.relative_to(component).as_posix()+'\n' for p in sorted(files)))
            else:
                for app in ('ttelegram','tspotify'):
                    for folder in ('wheels','runtime'):
                        shutil.rmtree(root/'components'/app/folder,ignore_errors=True)
            inventory={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()}
            manifest={'schema_version':1,'app_id':'ttools','version':__version__,
                      'platform':target_platform,'complete_suite_supported':target_platform=='linux-x86_64',
                      'unsupported_components':[] if target_platform=='linux-x86_64' else ['ttelegram'],
                      'files':inventory}
            (root/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
            verify_bundle(root)
            name=f'ttools-{target_platform}.zip';archive=output/name
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as package:
                for path in sorted(root.rglob('*')):
                    if path.is_file():package.write(path,path.relative_to(root.parent).as_posix())
            artifacts.append({'platform':target_platform,'url':f'https://github.com/user9x21imi/ttools/releases/download/v{__version__}/{name}',
                              'sha256':digest(archive),'complete_suite_supported':manifest['complete_suite_supported']})
            print(f'{name}: {archive.stat().st_size} bytes, complete={manifest["complete_suite_supported"]}')
    (output/'suite-update.json').write_text(json.dumps({'schema_version':1,'app_id':'ttools','version':__version__,'artifacts':artifacts},indent=2)+'\n')
    for name in ('install.sh','install.ps1','bootstrap.py'):
        shutil.copy2(ROOT/name,output/name)
    (output/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'dist');p.add_argument('--platform',action='append',choices=PLATFORMS);p.add_argument('--handoff',type=Path);a=p.parse_args()
    build(a.output,a.platform or PLATFORMS,a.handoff)
