"""Offline per-user native Windows installation; no pip, admin, WSL or tmux."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time,uuid,zipfile
from pathlib import Path
BUNDLE=Path(__file__).resolve().parent
sys.path.insert(0,str(BUNDLE/'source'))
from process_control import default_prefix,lock,running,stop

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
def verify(root):
    manifest=read(root/'files.json')
    for name,expected in manifest.items():
        file=(root/name).resolve()
        if not file.is_relative_to(root.resolve()) or not file.is_file() or digest(file)!=expected:raise RuntimeError('Integrity check failed: '+name)
    return manifest
def current(prefix):
    entry=read(prefix/'current.json');root=(prefix/'versions'/entry['version']).resolve()
    if not root.is_relative_to((prefix/'versions').resolve()) or not root.is_dir():raise RuntimeError('Invalid installed version')
    return root

def extract_wheel(wheel,target):
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if item.is_dir():continue
            parts=Path(item.filename).parts
            if not parts or '..' in parts or Path(item.filename).is_absolute():raise RuntimeError('Unsafe wheel member')
            if parts[0].endswith('.data'):
                if len(parts)<3 or parts[1] not in ('purelib','platlib'):continue
                parts=parts[2:]
            dest=target.joinpath(*parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(item))
def ensure_stopped(prefix,requested):
    if running(prefix):
        if not requested:raise RuntimeError('Telegram is running. Use --stop for a graceful save and exit.')
        stop(prefix)
def install(prefix,requested=False):
    if sys.platform!='win32':raise RuntimeError('This payload contains Windows x64 binaries. Install it on Windows x64.')
    verify(BUNDLE);version=(BUNDLE/'source/VERSION').read_text().strip();versions=prefix/'versions';versions.mkdir(parents=True,exist_ok=True)
    ensure_stopped(prefix,requested);dest=versions/version
    if dest.exists():verify(dest)
    else:
        stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=versions))
        try:
            shutil.copytree(BUNDLE/'bootstrap',stage/'runtime');shutil.copytree(BUNDLE/'source',stage/'source',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            packages=stage/'runtime/Lib/site-packages';packages.mkdir(parents=True)
            for wheel in sorted((BUNDLE/'wheels').glob('*.whl')):extract_wheel(wheel,packages)
            patch=read(stage/'source/vendor/patch.json')
            if digest(packages/'tg/views.py')!=patch['original_sha256'] or digest(stage/'source/vendor/views.py')!=patch['patched_sha256']:raise RuntimeError('Upstream view patch hashes do not match')
            shutil.copy2(stage/'source/vendor/views.py',packages/'tg/views.py')
            (stage/'runtime/python314._pth').write_text('python314.zip\n.\nLib\\site-packages\n..\\source\nimport site\n')
            shutil.copy2(BUNDLE/'manage.py',stage/'manage.py')
            # Installed manager uses a source-local process adapter; bootstrap manager remains portable.
            hashes={str(p.relative_to(stage)).replace('\\','/'):digest(p) for p in stage.rglob('*') if p.is_file()}
            write(stage/'files.json',hashes)
            result=subprocess.run([str(stage/'runtime/python.exe'),str(stage/'manage.py'),'doctor','--prefix',str(prefix),'--root',str(stage)],capture_output=True,text=True,encoding='utf-8',env=dict(os.environ,PYTHONUTF8='1'))
            if result.returncode:raise RuntimeError('Staged runtime failed validation: '+result.stdout+result.stderr)
            os.replace(stage,dest)
        finally:
            if stage.exists():shutil.rmtree(stage)
    if (prefix/'current.json').exists():
        previous=read(prefix/'current.json')
        if previous['version']!=version:write(prefix/'previous.json',previous)
    # Keep a stable manager + Python for the launcher, independent of the current pointer.
    if not (prefix/'bootstrap').exists():shutil.copytree(BUNDLE/'bootstrap',prefix/'bootstrap')
    (prefix/'manager-source').mkdir(exist_ok=True);shutil.copy2(BUNDLE/'source/process_control.py',prefix/'manager-source/process_control.py')
    manager=(BUNDLE/'manage.py').read_text(encoding='utf-8').replace("BUNDLE/'source'","BUNDLE/'manager-source'")
    (prefix/'manage.py').write_text(manager,encoding='utf-8')
    # Stable embedded interpreter imports only its standard library; entry uses runpy to locate manager.
    write(prefix/'current.json',{'version':version})
    (prefix/'ttelegram.cmd').write_text('@echo off\r\n"%~dp0bootstrap\\python.exe" -c "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name=\'__main__\')" "%~dp0" "%~dp0manage.py" launch --prefix "%~dp0." %*\r\n',encoding='utf-8')
    print(json.dumps({'installed':version,'prefix':str(prefix),'started':False}))
def doctor(root):
    report={'platform':sys.platform,'python':sys.version.split()[0],'root':str(root),'checks':{},'hardware_tested':False}
    checks=report['checks'];verify(root)
    try:
        if sys.platform!='win32':raise RuntimeError('Native Windows runtime must be checked on Windows')
        import ctypes
        from ctypes import wintypes
        checks['windows_64bit']=sys.maxsize>2**32
        import tdjson
        checks['tdlib']=json.loads(tdjson.td_execute(b'{"@type":"getOption","name":"version"}'))
        import PIL,qrcode,rlottie_python,sounddevice,imageio_ffmpeg,telegram,tg
        checks['imports']=True
        ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();result=subprocess.run([ffmpeg,'-version'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        checks['ffmpeg']=result.returncode==0
        # Import every platform module without creating a Telegram session or opening the microphone.
        import windows_bootstrap
        windows_bootstrap.install()
        import client,engine,media,windows_audio,windows_desktop,vtcurses
        checks['client_imports']=True
    except Exception as problem:report['error']=str(problem)
    report['ok']='error' not in report and all(v is not False for v in checks.values());print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['ok'] else 1

def rollback(prefix,requested=False):
    with lock(prefix/'run/manager.lock'):
        ensure_stopped(prefix,requested);old=read(prefix/'previous.json');target=(prefix/'versions'/old['version']).resolve()
        if not target.is_relative_to((prefix/'versions').resolve()):raise RuntimeError('Invalid rollback pointer')
        verify(target);now=read(prefix/'current.json');write(prefix/'current.json',old);write(prefix/'previous.json',now)
    return old

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['install','launch','version','stop','doctor','rollback','verify'])
    parser.add_argument('--prefix',type=Path,default=default_prefix());parser.add_argument('--root',type=Path);parser.add_argument('--stop',action='store_true');parser.add_argument('--in-terminal',action='store_true');parser.add_argument('--demo',action='store_true');parser.add_argument('--fast',action='store_true')
    args=parser.parse_args();prefix=args.prefix.resolve()
    if args.action=='install':
        with lock(prefix/'run/manager.lock'):install(prefix,args.stop)
        return 0
    if args.action=='stop':stop(prefix);print('Stopped');return 0
    if args.action=='verify':verify(BUNDLE);print('Bundle SHA-256 checks passed');return 0
    if args.action=='rollback':
        print(json.dumps(rollback(prefix,args.stop)));return 0
    root=args.root.resolve() if args.root else current(prefix)
    if args.action=='version':print((root/'source/VERSION').read_text().strip());return 0
    if args.action=='doctor':
        executable=root/'runtime/python.exe'
        if Path(sys.executable).resolve()!=executable.resolve():return subprocess.call([str(executable),str(root/'manage.py'),'doctor','--root',str(root),'--prefix',str(prefix)],env=dict(os.environ,PYTHONUTF8='1'))
        return doctor(root)
    if args.action=='launch':
        with lock(prefix/'run/manager.lock'):
            root=current(prefix)
            if running(prefix):raise RuntimeError('Telegram is already running')
            verify(root);env=dict(os.environ,TTELEGRAM_PREFIX=str(prefix),PYTHONUTF8='1')
            command=[str(root/'runtime/python.exe'),str(root/'source/windows_entry.py'),'--prefix',str(prefix)]+(['--demo'] if args.demo else [])+(['--fast'] if args.fast else [])
            if args.in_terminal:process=subprocess.Popen(command,env=env)
            else:
                terminal=shutil.which('wt.exe')
                if not terminal:raise RuntimeError('Install Windows Terminal 1.22 or later, or launch --in-terminal inside a SIXEL terminal')
                process=subprocess.Popen([terminal,'new-tab','--title','Telegram','--suppressApplicationTitle',*command],env=env)
            deadline=time.monotonic()+15
            while not running(prefix):
                if args.in_terminal and process.poll() is not None:return process.returncode
                if time.monotonic()>deadline:raise RuntimeError('Terminal launch did not establish the client instance lock. Check the terminal window and logs.')
                time.sleep(.05)
        return process.wait() if args.in_terminal else 0
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:print('ttelegram: '+str(error),file=sys.stderr);raise SystemExit(1)
