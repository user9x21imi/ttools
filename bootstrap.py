#!/usr/bin/env python3
"""Download an authenticated-origin release manifest and verify its ZIP before execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import venv
import zipfile

REPO='user9x21imi/ttools'

def read(url,limit):
    if urllib.parse.urlsplit(url).scheme!='https':raise ValueError('HTTPS required')
    request=urllib.request.Request(url,headers={'User-Agent':'ttools-bootstrap/1'})
    with urllib.request.urlopen(request,timeout=30) as response:
        if urllib.parse.urlsplit(response.geturl()).scheme!='https':raise ValueError('HTTPS redirect required')
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Download too large')
        return data

def target_platform():
    system={'Linux':'linux','Darwin':'macos','Windows':'windows'}.get(platform.system())
    arch={'x86_64':'x86_64','amd64':'x86_64','arm64':'arm64','aarch64':'arm64'}.get(platform.machine().lower())
    if not system or not arch:raise RuntimeError('Unsupported OS/architecture')
    return system+'-'+arch

def python314(prefix):
    if sys.version_info[:2]==(3,14):return Path(sys.executable)
    # uv's managed CPython is kept outside versioned releases, so rollback remains usable.
    root=prefix/'bootstrap-venv'
    venv.EnvBuilder(with_pip=True).create(root)
    py=root/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(py),'-m','pip','install','--disable-pip-version-check','uv>=0.9,<1'],check=True)
    uv=root/('Scripts/uv.exe' if os.name=='nt' else 'bin/uv')
    env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(prefix/'python'))
    subprocess.run([str(uv),'python','install','3.14'],env=env,check=True)
    return Path(subprocess.check_output([str(uv),'python','find','--managed-python','3.14'],env=env,text=True).strip())

def prepare_linux(selected):
    if platform.system()!='Linux':return
    needed=['curl','ip','flock','sudo','visudo'] if 'tvpn' in selected else []
    if 'ttelegram' in selected:needed+=['tmux','ffmpeg','ffprobe','ffplay','kdialog','pactl']
    missing=[x for x in needed if not shutil.which(x)]
    gi=True
    if 'ttelegram' in selected:
        gi=subprocess.run(['/usr/bin/python3','-c','import gi;gi.require_version("Gtk","3.0");from gi.repository import Gtk'],capture_output=True).returncode==0
    if not missing and gi:return
    if Path('/etc/steamos-release').exists():
        raise RuntimeError('SteamOS: missing system packages '+', '.join(missing)+'. The installer will not disable the read-only system. See docs/INSTALL.md.')
    if shutil.which('apt-get'):
        packages=['curl','iproute2','util-linux','sudo']
        if 'ttelegram' in selected:packages+=['tmux','ffmpeg','kdialog','pulseaudio-utils','python3-gi','gir1.2-gtk-3.0']
        subprocess.run(['sudo','apt-get','update'],check=True)
        subprocess.run(['sudo','apt-get','install','-y',*packages],check=True)
    elif shutil.which('dnf'):
        raise RuntimeError('Install tmux, ffmpeg/ffplay, kdialog, pulseaudio-utils, python3-gobject, GTK3, iproute and sudo using your distribution, then rerun. ffmpeg availability varies by enabled repositories.')
    else:raise RuntimeError('Missing system prerequisites: '+', '.join(missing)+'. See docs/INSTALL.md.')

def main():
    if os.name=='nt':
        os.environ['PYTHONUTF8']='1'
        os.environ['PYTHONIOENCODING']='utf-8'
        for stream in (sys.stdout,sys.stderr):
            if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    p=argparse.ArgumentParser(description='One-command ttools suite bootstrap')
    p.add_argument('--prefix');p.add_argument('--allow-partial',action='store_true');p.add_argument('--release');p.add_argument('--preview',action='store_true')
    p.add_argument('--components',default='tspotify,ttelegram,tvpn,tthings');p.add_argument('--no-system-deps',action='store_true')
    args=p.parse_args()
    target=target_platform()
    selected=args.components.split(',')
    # Reject unsupported complete installations before downloading/installing anything.
    if target not in ('linux-x86_64','windows-x86_64') and 'ttelegram' in selected and not args.allow_partial:
        p.error('Telegram is packaged for Linux x86_64 and preview Windows x64. A complete native suite is not available for this OS. --allow-partial installs the supported applications explicitly.')
    if args.prefix:prefix=Path(args.prefix).expanduser().resolve()
    elif os.name=='nt':prefix=Path(os.environ['LOCALAPPDATA'])/'ttools'
    elif platform.system()=='Darwin':prefix=Path.home()/'Library/Application Support/ttools'
    else:prefix=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'ttools-suite'
    endpoint=f'https://api.github.com/repos/{REPO}/releases'+('/tags/'+args.release if args.release else '?per_page=10')
    data=json.loads(read(endpoint,2*1024*1024))
    releases=[data] if args.release else data
    release=next((r for r in releases if not r.get('draft') and (args.preview or not r.get('prerelease')) and any(a['name']=='suite-update.json' for a in r.get('assets',[]))),None)
    if not release:raise RuntimeError('No published suite release in this channel')
    manifest_asset=next(a for a in release['assets'] if a['name']=='suite-update.json')
    manifest=json.loads(read(manifest_asset['browser_download_url'],2*1024*1024))
    if manifest.get('schema_version')!=1 or manifest.get('app_id')!='ttools':raise ValueError('Invalid update manifest')
    artifact=next((a for a in manifest['artifacts'] if a['platform']==target),None)
    if not artifact:raise RuntimeError('No release for '+target)
    archive_data=read(artifact['url'],700*1024*1024)
    if hashlib.sha256(archive_data).hexdigest()!=artifact['sha256']:raise ValueError('SHA-256 mismatch; nothing was installed')
    with tempfile.TemporaryDirectory(prefix='ttools-bootstrap-') as folder:
        folder=Path(folder);archive=folder/'suite.zip';archive.write_bytes(archive_data)
        # Use the same validator as the runtime updater after validating outer members.
        with zipfile.ZipFile(archive) as package:
            members=package.infolist()
            if len(members)>50000 or sum(x.file_size for x in members)>2*1024**3:raise ValueError('Archive too large')
            for item in members:
                name=item.orig_filename;path=PurePosixPath(name);kind=stat.S_IFMT(item.external_attr>>16)
                if not name or '\0' in name or name.startswith('/') or path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name or kind not in (0,stat.S_IFREG,stat.S_IFDIR):raise ValueError('Unsafe archive member')
            package.extractall(folder/'unpacked')
        bundle=folder/'unpacked/ttools'
        sys.path.insert(0,str(bundle))
        from ttools.distribution import verify_bundle
        info=verify_bundle(bundle)
        if info['version']!=manifest['version'] or info['platform']!=target:raise ValueError('Wrong bundle version/platform')
        if not args.no_system_deps:prepare_linux(selected)
        py=python314(prefix)
        argv=[str(py),str(bundle/'installer.py'),'--prefix',str(prefix),'--components',args.components]
        if args.allow_partial:argv.append('--allow-partial')
        subprocess.run(argv,check=True)
        if args.preview:
            (prefix/'channel').write_text('preview',encoding='utf-8')
    print('Installed. Open a new terminal and run: ttools')
    if args.allow_partial and target.startswith('macos'):print('Partial installation: Telegram is not included on macOS.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print('ttools: '+str(error),file=sys.stderr);raise SystemExit(1)
