#!/usr/bin/env python3
"""Produce platform-labeled ZIPs, complete inventories and the update feed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile
import zipfile
import tomllib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ttools import __version__
from ttools.distribution import digest,verify_bundle,validate_component_versions,valid_source_commit

PLATFORMS=('linux-x86_64','macos-arm64','macos-x86_64','windows-x86_64')
EXCLUDE={'__pycache__','.git','.venv','.pytest_cache','build','dist'}

def suite_version_for_package(package):
    """Map supported PEP 440 suite metadata to the public release version."""
    match=re.fullmatch(r'(\d+\.\d+\.\d+)(?:\.dev(\d+))?',package)
    if not match:raise RuntimeError(f'Unsupported Python package version: {package}')
    base,preview=match.groups()
    return f'{base}-preview.{preview}' if preview is not None else base

def validate_release_versions(root=ROOT):
    """Reject ambiguous package/suite versions and stale component catalogs."""
    package=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    expected=suite_version_for_package(package)
    if __version__!=expected:
        raise RuntimeError(f'Suite version mismatch: pyproject={package} maps to {expected}, launcher={__version__}')
    validate_component_versions(root,strict=True)

def resolve_source_commit(root=ROOT):
    """Bind release bytes to the exact clean Git commit used for the build."""
    try:
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','--verify','HEAD^{commit}'],text=True).strip().lower()
        status=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=normal'],text=True)
    except (OSError,subprocess.CalledProcessError) as error:
        raise RuntimeError('Release provenance requires a Git checkout') from error
    if not valid_source_commit(head):raise RuntimeError('Git did not return a full commit SHA')
    expected=os.environ.get('GITHUB_SHA','').lower()
    if expected and expected!=head:raise RuntimeError(f'Checked-out commit {head} does not match GITHUB_SHA {expected}')
    if status.strip():raise RuntimeError('Release build requires a clean checkout')
    return head

def copy_tree(source,target):
    for path in source.rglob('*'):
        rel=path.relative_to(source)
        if not path.is_file() or path.is_symlink() or any(x in EXCLUDE for x in rel.parts) or path.suffix=='.pyc':continue
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)

def build(output,platforms=PLATFORMS,handoff=None,source_commit=None):
    validate_release_versions()
    resolved_commit=resolve_source_commit()
    if source_commit is not None and source_commit.lower()!=resolved_commit:
        raise RuntimeError('Requested source commit does not match the clean checkout')
    source_commit=resolved_commit
    output.mkdir(parents=True,exist_ok=True)
    artifacts=[]
    for target_platform in platforms:
        with tempfile.TemporaryDirectory(prefix='ttools-package-') as temporary:
            root=Path(temporary)/'ttools';root.mkdir()
            for directory in ('ttools','components','konsole','scripts'):
                copy_tree(ROOT/directory,root/directory)
            for name in ('installer.py','bootstrap.py','install-local.py','README.md','README.en.md','LICENSE','THIRD_PARTY.md','icon.svg','logo.svg'):
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
                        if app=='ttelegram' and folder=='runtime' and target_platform=='windows-x86_64':continue
                        shutil.rmtree(root/'components'/app/folder,ignore_errors=True)
            if target_platform=='windows-x86_64':
                native=root/'components/ttelegram/runtime/windows-native'
                if not (native/'files.json').is_file():raise RuntimeError('Run tools/download_windows_telegram.py before building Windows')
            else:
                shutil.rmtree(root/'components/ttelegram/runtime',ignore_errors=True)
            inventory={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()}
            manifest={'schema_version':2,'app_id':'ttools','version':__version__,'source_commit':source_commit,
                      'platform':target_platform,'complete_suite_supported':target_platform=='linux-x86_64',
                      'unsupported_components':([] if target_platform=='linux-x86_64' else
                                                ['tsoundcloud']+([] if target_platform=='windows-x86_64' else ['ttelegram'])),
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
    (output/'suite-update.json').write_text(json.dumps({'schema_version':2,'app_id':'ttools','version':__version__,'source_commit':source_commit,'artifacts':artifacts},indent=2)+'\n')
    for name in ('install.sh','install.ps1','bootstrap.py'):
        shutil.copy2(ROOT/name,output/name)
    (output/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'dist');p.add_argument('--platform',action='append',choices=PLATFORMS);p.add_argument('--handoff',type=Path);a=p.parse_args()
    build(a.output,a.platform or PLATFORMS,a.handoff)
