#!/usr/bin/env python3
"""Offline install-only and hash-checked artifact updates. Never opens Telegram."""
import argparse,contextlib,fcntl,hashlib,json,os,platform,shlex,shutil,signal,subprocess,sys,tarfile,tempfile,time,urllib.request,venv
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def socket(prefix):return 'ttelegram-'+hashlib.sha256(str(prefix).encode()).hexdigest()[:12]
def tm(prefix,*args):return subprocess.run(['tmux','-L',socket(prefix),*args],capture_output=True,text=True)
def running(prefix):return tm(prefix,'has-session','-t','telegram').returncode==0
def stop(prefix):
    if not running(prefix):return
    current=(prefix/'current').resolve()
    env=os.environ.copy();env['TTELEGRAM_SOCKET']=socket(prefix)
    subprocess.run([str(current/'venv/bin/python'),str(current/'session_control.py')],env=env,check=True)
    for _ in range(100):
        if not running(prefix):return
        time.sleep(.1)
    raise RuntimeError('Worker did not exit gracefully; update cancelled without changing current')
def checks():
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise RuntimeError('Only Linux x86_64 supported')
    if sys.version_info[:2]!=(3,14):raise RuntimeError('This offline artifact requires CPython 3.14')
    for exe in ('tmux','ffmpeg','ffprobe','ffplay','kdialog','pactl'):
        if not shutil.which(exe):raise RuntimeError('Install system prerequisite: '+exe)
    subprocess.run(['/usr/bin/python3','-c','import gi;gi.require_version("Gtk","3.0");from gi.repository import Gtk'],check=True,capture_output=True)
    version=subprocess.check_output(['tmux','-V'],text=True).strip()
    if tuple(map(int,__import__('re').search(r'(\d+)\.(\d+)',version).groups()))<(3,4):raise RuntimeError('tmux >=3.4 required')
def verify(bundle):
    for line in (bundle/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);file=(bundle/name).resolve()
        if not file.is_relative_to(bundle.resolve()) or not file.is_file() or sha(file)!=digest:raise RuntimeError('Checksum mismatch: '+name)
def activate(prefix,target):
    link=prefix/'.current-next';link.unlink(missing_ok=True);link.symlink_to(target);os.replace(link,prefix/'current')
def install(bundle,prefix,allow_stop=False):
    checks();verify(bundle)
    if running(prefix):
        if not allow_stop:raise RuntimeError('Client running; pass --stop for graceful exit before update')
        stop(prefix)
    source=bundle/'source';version=(source/'VERSION').read_text().strip()
    if not __import__('re').fullmatch(r'[A-Za-z0-9._-]+',version):raise RuntimeError('Invalid version')
    release=prefix/'releases'/version
    if release.exists():
        expected=json.loads((source/'MANIFEST.json').read_text())
        if (release/'MANIFEST.json').read_text()!=(source/'MANIFEST.json').read_text():raise RuntimeError('Same version has different content')
        for name,digest in expected.items():
            if sha(release/name)!=digest:raise RuntimeError('Existing release modified: '+name)
    else:
        staging=Path(tempfile.mkdtemp(prefix='.install-',dir=prefix))
        try:
            shutil.copytree(source,staging,dirs_exist_ok=True)
            venv.EnvBuilder(with_pip=True).create(staging/'venv')
            python=staging/'venv/bin/python'
            subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--find-links',str(bundle/'wheels'),'-r',str(staging/'requirements.txt')],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            site=Path(subprocess.check_output([str(python),'-c','import sysconfig;print(sysconfig.get_paths()["purelib"])'],text=True).strip())
            patch=json.loads((source/'vendor/patch.json').read_text());target=site/patch['target']
            if sha(target)!=patch['original_sha256']:raise RuntimeError('Unsupported tg source; refusing patch')
            shutil.copy2(source/'vendor/views.py',target)
            subprocess.run([str(python),'-c','import client,engine,media,sticker_gallery,voice_recorder,voice_inline;from telegram.tdjson import TDJson;t=TDJson();print("Runtime imports and TDLib load OK")'],cwd=staging,check=True,capture_output=True,text=True)
            release.parent.mkdir(parents=True,exist_ok=True);staging.rename(release)
        finally:
            if staging.exists():shutil.rmtree(staging)
    old=(prefix/'current').resolve() if (prefix/'current').exists() else None
    if old and old!=release:
        previous=prefix/'previous';previous.unlink(missing_ok=True);previous.symlink_to(old)
    activate(prefix,release)
    (prefix/'bin').mkdir(exist_ok=True)
    launch='#!/bin/sh\nexport TTELEGRAM_SOCKET='+shlex.quote(socket(prefix))+'\nexec '+shlex.quote(str(prefix/'current/venv/bin/python'))+' '+shlex.quote(str(prefix/'current/ui.py'))+' "$@"\n'
    (prefix/'bin/ttelegram').write_text(launch);(prefix/'bin/ttelegram').chmod(0o755)
    shutil.copy2(Path(__file__),prefix/'manage.py') if Path(__file__).resolve()!=prefix/'manage.py' else None
    print(json.dumps({'installed':version,'prefix':str(prefix),'launched':False}))
def update(manifest,prefix,allow_stop):
    if manifest.startswith('https://'):
        with urllib.request.urlopen(manifest,timeout=30) as response:data=json.load(response)
        base=None
    elif '://' in manifest:raise RuntimeError('Manifest requires HTTPS or a local file')
    else:
        base=Path(manifest).resolve().parent;data=json.loads(Path(manifest).read_text())
    if data.get('schema_version')!=1 or data.get('app_id')!='ttelegram':raise RuntimeError('Wrong update manifest')
    item=next(x for x in data['artifacts'] if x['platform']=='linux-x86_64')
    with tempfile.TemporaryDirectory(prefix='ttelegram-update-') as folder:
        folder=Path(folder);archive=folder/'release.tar.gz'
        if item.get('url'):
            if not item['url'].startswith('https://'):raise RuntimeError('Artifact requires HTTPS')
            with urllib.request.urlopen(item['url'],timeout=60) as response,archive.open('wb') as out:shutil.copyfileobj(response,out)
        elif base and item.get('local_path'):shutil.copy2(base/item['local_path'],archive)
        else:raise RuntimeError('No published artifact or local artifact path')
        if sha(archive)!=item['sha256']:raise RuntimeError('Artifact SHA-256 mismatch')
        dest=folder/'bundle';dest.mkdir()
        with tarfile.open(archive) as tar:
            if any(m.issym() or m.islnk() or not (m.isfile() or m.isdir()) for m in tar.getmembers()):raise RuntimeError('Unsafe archive member')
            tar.extractall(dest,filter='data')
        if (dest/'source/VERSION').read_text().strip()!=data['version']:raise RuntimeError('Version mismatch')
        install(dest,prefix,allow_stop)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prefix',required=True,type=Path);ap.add_argument('--manifest');ap.add_argument('--stop',action='store_true');ap.add_argument('--stop-only',action='store_true');ap.add_argument('--version',action='store_true');ap.add_argument('--rollback',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args()
    prefix=args.prefix.expanduser().resolve();prefix.mkdir(parents=True,exist_ok=True)
    with (prefix/'.install.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.version:print((prefix/'current/VERSION').read_text().strip());return
        if args.stop_only:stop(prefix);print('Stopped own session');return
        if args.rollback:
            if running(prefix):
                if not args.stop:raise RuntimeError('Client running; --stop required')
                stop(prefix)
            previous=(prefix/'previous').resolve(strict=True);activate(prefix,previous);print('Rolled back');return
        if args.check:checks();print('Prerequisites OK');return
        if args.manifest:update(args.manifest,prefix,args.stop)
        else:install(Path(__file__).resolve().parent,prefix,args.stop)
if __name__=='__main__':
    try:main()
    except Exception as error:print('ttelegram: '+str(error),file=sys.stderr);sys.exit(1)
