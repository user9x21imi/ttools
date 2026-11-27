"""Install-only suite lifecycle. All downloaded code is hash-checked before use."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import venv

from .distribution import (atomic_json, digest, extract_zip, fetch, latest_suite_manifest, locked,
                           platform_id, prefix_path, verify_bundle, version_key, configure_text_io,
                           valid_source_commit)

NATIVE_TRAMPOLINE = "import runpy,sys;runpy.run_path(sys.argv.pop(1),run_name='__main__')"
APP_IDS = ('tspotify','tsoundcloud','ttelegram','tthings','tvpn')
# Components that have a real native package for a platform. SoundCloud has no
# Windows build, so it is excluded from the standard Windows installation.
WINDOWS_COMPONENTS = ('tspotify','ttelegram','tthings','tvpn')
UNSUPPORTED_BY_PLATFORM = {'windows-x86_64': ('tsoundcloud',)}

def supported_components(target_platform):
    """APP_IDS minus components with no native package for target_platform."""
    blocked = set(UNSUPPORTED_BY_PLATFORM.get(target_platform, ()))
    return [a for a in APP_IDS if a not in blocked]

def default_components(target_platform=None):
    """Default component selection; on Windows never include unsupported apps."""
    if target_platform is None:
        target_platform = platform_id()
    return supported_components(target_platform)

def run(argv, **kwargs):
    print('+ '+ ' '.join(map(str,argv)),flush=True)
    subprocess.run(list(map(str,argv)),check=True,**kwargs)

def powershell_exe():
    """Prefer PowerShell 7+; fall back to in-box Windows PowerShell 5.1."""
    if os.name!='nt':return 'powershell.exe'
    return shutil.which('pwsh.exe') or shutil.which('pwsh') or shutil.which('powershell.exe') or 'powershell.exe'

def python_in(directory):
    return directory/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def create_venv(directory):
    venv.EnvBuilder(with_pip=True).create(directory)
    return python_in(directory)

def install_pip(python,*args):
    run([python,'-m','pip','install','--disable-pip-version-check',*args])

def plan(bundle, target_platform, selected, allow_partial=False):
    versions=json.loads((bundle/'components/versions.json').read_text(encoding='utf-8'))
    unsupported=[]
    for app in selected:
        if app not in APP_IDS:raise ValueError(f'Unknown component: {app}')
        if app=='ttelegram' and target_platform!='linux-x86_64' and not (target_platform=='windows-x86_64' and (bundle/'components/ttelegram/windows-native/app.json').is_file()):unsupported.append(app)
        if app=='tsoundcloud' and target_platform!='linux-x86_64':unsupported.append(app)
        if app=='tvpn' and target_platform not in ('linux-x86_64','macos-arm64','macos-x86_64','windows-x86_64'):unsupported.append(app)
    if unsupported and not allow_partial:
        raise RuntimeError(f'{target_platform}: no supported package for {", ".join(unsupported)}. Полный комплект для этой ОС пока недоступен; --allow-partial разрешает явно неполную установку.')
    if target_platform=='windows-x86_64' and 'ttelegram' not in unsupported and 'ttelegram' in selected:
        versions['ttelegram']=json.loads((bundle/'components/ttelegram/windows-native/app.json').read_text())['version']
    return {'platform':target_platform,'install':[a for a in APP_IDS if a in selected and a not in unsupported],
            'unsupported':unsupported,'versions':versions,'complete':not unsupported and set(selected)==set(APP_IDS)}

def linux_prerequisites(selected,defer_system):
    if 'ttelegram' in selected:
        from importlib.util import spec_from_file_location,module_from_spec
        # Load checks without executing the component installer's main().
        if sys.version_info[:2]!=(3,14):
            raise RuntimeError('Telegram bundle requires Python 3.14. Use the bootstrap installer to prepare it.')
        missing=[x for x in ('tmux','ffmpeg','ffprobe','ffplay','kdialog','pactl') if not shutil.which(x)]
        if missing:raise RuntimeError('Missing Telegram system packages: '+', '.join(missing)+'. See docs/INSTALL.md.')
        subprocess.run(['/usr/bin/python3','-c','import gi;gi.require_version("Gtk","3.0");from gi.repository import Gtk'],check=True,capture_output=True)
    if 'tvpn' in selected and not defer_system:
        missing=[x for x in ('sudo','visudo','ip','curl','flock') if not shutil.which(x,path=os.environ.get('PATH','')+os.pathsep+'/usr/sbin'+os.pathsep+'/sbin')]
        if missing:raise RuntimeError('Missing VPN prerequisites: '+', '.join(missing))

def source_entry(path,module,source):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('import runpy,sys\nsys.path.insert(0,'+repr(str(source))+')\nrunpy.run_module('+repr(module)+',run_name="__main__")\n',encoding='utf-8')
    return path

def install_component(app,release,defer_system=False):
    bundle=release/'components'/app
    source=bundle/'source'
    dest=release/'apps'/app
    dest.mkdir(parents=True,exist_ok=True)
    env={}
    if app=='tspotify':
        archive=bundle/'runtime/tspotify-linux-x86_64.zip'
        if sys.platform=='linux' and archive.is_file() and tuple(int(x) for x in platform.libc_ver()[1].split('.')[:2])>=(2,43):
            run([sys.executable,bundle/'install.py','--prefix',dest,'--manifest',bundle/'update.json','--archive',archive])
            command=[str(dest/'bin/tspotify')]
        else:
            py=create_venv(dest/'venv')
            install_pip(py,str(source))
            command=[str(py),'-m','tspotify']
            env['TSPOTIFY_INSTALL_PREFIX']=str(dest)
            run([*command,'verify-runtime'])
        return command,env
    if app=='ttelegram':
        if os.name=='nt':
            native=bundle/'runtime/windows-native'
            run([native/'bootstrap/python.exe','-c',NATIVE_TRAMPOLINE,native/'manage.py','install','--prefix',dest,'--stop'])
            return [str(dest/'bootstrap/python.exe'),'-c',NATIVE_TRAMPOLINE,str(dest/'manage.py'),'launch','--prefix',str(dest),'--in-terminal'],env
        run([sys.executable,bundle/'install.py','--prefix',dest])
        return [str(dest/'bin/ttelegram')],env
    if app=='tthings':
        py=Path(sys.executable)
        if os.name=='nt' or sys.platform=='darwin':
            py=create_venv(dest/'venv')
            install_pip(py,'psutil>=7.0','tzdata>=2025.2')
        entry=source_entry(dest/'entry.py','tthings',source)
        atomic_json(dest/'.tthings/install.json',{'app_id':'tthings','version':json.loads((release/'components/versions.json').read_text(encoding='utf-8'))['tthings']})
        env['TTOOLS_TTHINGS_PREFIX']=str(dest)
        command=[str(py),str(entry)]
        run([*command,'--version'])
        return command,env
    if app=='tsoundcloud':
        command=[sys.executable,bundle/'launch.py']
        run([*command,'--version'])
        return command,env
    if app=='tvpn':
        if sys.platform=='linux':
            command=[sys.executable,source/'install.py','--prefix',dest,'--no-launch']
            if defer_system:command+=['--defer-system']
            run(command)
            return ['bash',str(dest/'Riseup-Amsterdam-SteamDeck.sh')],env
        shutil.copytree(source,dest,dirs_exist_ok=True)
        py=create_venv(dest/'.venv')
        requirements='requirements-windows.txt' if os.name=='nt' else 'requirements-macos.txt'
        install_pip(py,'-r',str(dest/requirements))
        if not defer_system:
            if os.name=='nt':
                setup=dest/'platforms/windows/install.ps1'
                # Setup dependencies and UAC are handled by a purpose-built local script.
                run([powershell_exe(),'-NoProfile','-File',str(release/'scripts/setup-vpn-windows.ps1'),'-Setup',str(setup)])
            else:
                run(['bash',str(dest/'platforms/macos/install.sh')])
        return [str(py),str(dest/'launch.py')],env
    raise ValueError(app)

def _write_shortcuts(prefix,shortcuts=True,components=APP_IDS):
    root=Path(__file__).resolve().parents[1]
    runner=prefix/'runner.py'
    runner.write_text('''import json,os,sys
from pathlib import Path
prefix=Path(__file__).resolve().parent
state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
release=Path(state['release'])
os.environ['TTOOLS_PREFIX']=str(prefix)
os.environ['TTOOLS_CATALOG']=str(release/'apps.local.json')
sys.path.insert(0,str(release))
from ttools.suite import launch_installed
try:
    raise SystemExit(launch_installed(prefix,sys.argv[1:]))
except (OSError,ValueError,RuntimeError) as error:
    print('ttools: '+str(error),file=sys.stderr)
    raise SystemExit(1)
''',encoding='utf-8')
    if not shortcuts:return
    if os.name=='nt':
        commands=prefix/'bin';commands.mkdir(exist_ok=True)
        for app in ('ttools',*components):
            args='' if app=='ttools' else '--app '+app+' '
            (commands/(app+'.cmd')).write_text('@echo off\r\nchcp 65001 >nul\r\nset "PYTHONUTF8=1"\r\nset "PYTHONIOENCODING=utf-8"\r\n"'+sys.executable+'" "'+str(runner)+'" '+args+'%*\r\n',encoding='utf-8')
        # Update the user PATH, never the system PATH.
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_READ|winreg.KEY_WRITE) as key:
            try:value,_=winreg.QueryValueEx(key,'Path')
            except FileNotFoundError:value=''
            parts=[x for x in value.split(';') if x.strip()]
            if str(commands).casefold() not in [x.casefold() for x in parts]:
                parts.append(str(commands))
                winreg.SetValueEx(key,'Path',0,winreg.REG_EXPAND_SZ,';'.join(parts))
    else:
        import shlex
        commands=Path.home()/'.local/bin';commands.mkdir(parents=True,exist_ok=True)
        for app in ('ttools',*components):
            args='' if app=='ttools' else '--app '+app+' '
            wrapper=commands/app
            wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(runner))+' '+args+'"$@"\n')
            wrapper.chmod(0o755)
        if sys.platform=='linux':
            konsole=Path.home()/'.local/share/konsole';konsole.mkdir(parents=True,exist_ok=True)
            for source in (root/'konsole').glob('*'):
                shutil.copy2(source,konsole/source.name)
            desktop=Path.home()/'.local/share/applications/ttools.desktop';desktop.parent.mkdir(parents=True,exist_ok=True)
            exe='konsole --separate -e "'+str(commands/'ttools')+'"' if shutil.which('konsole') else '"'+str(commands/'ttools')+'"'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=ttools\nExec='+exe+'\nTerminal='+('false' if shutil.which('konsole') else 'true')+'\nIcon=utilities-terminal\nCategories=Utility;\n',encoding='utf-8')
        elif sys.platform=='darwin':
            app=Path.home()/'Applications/ttools.command';app.parent.mkdir(exist_ok=True)
            app.write_text('#!/bin/sh\nexec '+shlex.quote(str(commands/'ttools'))+'\n');app.chmod(0o755)


def stop_previous_background_apps(state):
    """A detached tmux or effect window must not outlive an installation transition."""
    if not state:return
    release=Path(state['release'])
    catalog=release/'apps.local.json'
    if not catalog.is_file():return
    apps=json.loads(catalog.read_text(encoding='utf-8'))['apps']
    for app in apps:
        dest=release/'apps'/app['id']
        if not dest.is_dir():continue
        env=dict(os.environ,**app.get('env',{}))
        if app['id']=='ttelegram':
            if os.name=='nt':
                run([dest/'bootstrap/python.exe','-c',NATIVE_TRAMPOLINE,dest/'manage.py','stop','--prefix',dest],env=env)
            else:
                run([sys.executable,dest/'manage.py','--prefix',dest,'--stop-only'],env=env)
        elif app['id']=='tspotify':
            run([*app['command'],'stop','--timeout','15'],env=env)
            # Demo has no control endpoint; its managed runtime lock still excludes updates.
            with (dest/'run.lock').open('a+b') as stream:
                if os.name=='posix':
                    import fcntl
                    try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except OSError:raise RuntimeError('Spotify is still running; update cancelled') from None
                else:
                    import msvcrt
                    stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
                    try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                    except OSError:raise RuntimeError('Spotify is still running; update cancelled') from None
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        elif app['id']=='tthings':
            if sys.platform=='linux':
                run([*app['command'],'--stop-managed','--prefix',dest],env=env)
            elif list((dest/'.tthings/instances').glob('*.json')):
                raise RuntimeError('Close tthings windows before updating this platform')
        elif app['id']=='tvpn':
            run([sys.executable,dest/'manage.py','stop','--timeout','30'],env=env)


def configure_tvpn_system(release,target):
    """Apply the versioned TVPN system integration only after suite activation."""
    release=Path(release)
    dest=release/'apps/tvpn'
    if target=='linux-x86_64':
        run(['bash',dest/'install-passwordless.sh'])
    elif target.startswith('macos-'):
        run(['bash',dest/'platforms/macos/install.sh'])
    elif target=='windows-x86_64':
        run([powershell_exe(),'-NoProfile','-File',release/'scripts/setup-vpn-windows.ps1',
             '-Setup',dest/'platforms/windows/install.ps1'])
    else:
        raise RuntimeError(f'No TVPN system setup for {target}')


def _validate_release_state(prefix,state):
    """Validate a versioned suite pointer before it can become active again."""
    releases=(prefix/'releases').resolve()
    try:
        release=Path(state['release']).resolve()
        if not release.is_relative_to(releases):
            raise ValueError
        manifest=json.loads((release/'bundle.json').read_text(encoding='utf-8'))
    except (KeyError,OSError,ValueError,TypeError) as error:
        raise RuntimeError('Suite release metadata is missing or outside the managed prefix') from error
    if (manifest.get('app_id')!='ttools' or manifest.get('version')!=state.get('version')
            or manifest.get('platform')!=state.get('platform')
            or manifest.get('source_commit')!=state.get('source_commit')
            or not isinstance(manifest.get('files'),dict)):
        raise RuntimeError('Suite release metadata does not match its activation state')
    for name,expected in manifest['files'].items():
        path=(release/name).resolve()
        if not path.is_relative_to(release) or not path.is_file() or digest(path)!=expected:
            raise RuntimeError(f'Suite release file does not match its manifest: {name}')
    return release


def install(bundle,prefix,selected=APP_IDS,allow_partial=False,defer_system=False,shortcuts=True):
    bundle=Path(bundle).resolve();prefix=prefix_path(prefix)
    manifest=verify_bundle(bundle)
    target=platform_id()
    if manifest.get('platform')!=target:
        raise ValueError(f'Wrong bundle platform: {manifest.get("platform")} != {target}')
    proposed=plan(bundle,target,selected,allow_partial)
    if sys.platform=='linux':linux_prerequisites(proposed['install'],defer_system)
    with locked(prefix):
        state_path=prefix/'state.json'
        old=json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else None
        build_id=manifest['version']+'-'+digest(bundle/'bundle.json')[:12]
        options={'components':list(selected),'allow_partial':allow_partial,'defer_system':defer_system,'shortcuts':shortcuts}
        if old and old.get('build_id')==build_id and old.get('options')==options:
            print('Suite already installed; no files changed.')
            return old
        if old and 'tvpn' in proposed['install']:
            installed_vpn=Path(old['release'])/'apps/tvpn/VERSION'
            if installed_vpn.is_file() and version_key(installed_vpn.read_text(encoding='utf-8').strip())>version_key(proposed['versions']['tvpn']):
                raise RuntimeError('This suite contains an older TVPN than the installed native update; refusing to downgrade the protected backend')
        stop_previous_background_apps(old)
        release=prefix/'releases'/build_id
        if release.exists():
            # An inactive completed release may still be a rollback target. Never remove it.
            release=prefix/'releases'/(build_id+'-'+str(time.time_ns()))
        release.parent.mkdir(parents=True,exist_ok=True)
        state_committed=False
        tvpn_setup_attempted=False
        try:
            # Keep an incomplete copy out of the active catalog and remove it
            # on ENOSPC just like any later installer failure.
            shutil.copytree(bundle,release)
            # The launcher needs windows-curses; Unix ships curses with Python.
            if os.name=='nt':
                launcher_python=create_venv(release/'launcher-venv')
                install_pip(launcher_python,'windows-curses>=2.4')
            else:launcher_python=Path(sys.executable)
            apps=[]
            for app in proposed['install']:
                # Protected TVPN files are changed after every fallible
                # component install and after the candidate state is written.
                command,env=install_component(app,release,defer_system or app=='tvpn')
                app_manifest=release/'components'/app/'app.json'
                app_name=json.loads(app_manifest.read_text(encoding='utf-8')).get('name',app) if app_manifest.is_file() else app
                apps.append({'id':app,'name':app_name,'version':proposed['versions'][app],
                             'command':command,'env':env,'update_owner':'ttools' if app!='tvpn' else 'tvpn',
                             'suite_managed':True})
            atomic_json(release/'apps.local.json',{'schema_version':1,'apps':apps})
            state={'schema_version':1,'version':manifest['version'],'source_commit':manifest.get('source_commit'),
                   'build_id':build_id,'release':str(release),
                   'python':str(launcher_python),'platform':target,'complete':proposed['complete'] and not (defer_system and 'tvpn' in proposed['install']),
                   'unsupported':proposed['unsupported'],'options':options,'installed_at':time.time()}
            if old:state['previous']=old
            # Prevent an unbounded nested history in state.json.
            if old and 'previous' in old:old.pop('previous')
            atomic_json(state_path,state)
            state_committed=True
            try:
                _write_shortcuts(prefix,shortcuts,proposed['install'])
            except BaseException:
                if old:atomic_json(state_path,old)
                else:state_path.unlink(missing_ok=True)
                state_committed=False
                raise
            if 'tvpn' in proposed['install'] and not defer_system:
                tvpn_setup_attempted=True
                configure_tvpn_system(release,target)
        except BaseException:
            if state_committed:
                if old:atomic_json(state_path,old)
                else:state_path.unlink(missing_ok=True)
            # TVPN's Linux helper is transactional; when an older suite exists,
            # reapply its protected backend if platform setup failed partway.
            if tvpn_setup_attempted and old and 'tvpn' in old.get('options',{}).get('components',[]) and not old.get('options',{}).get('defer_system',False):
                try:configure_tvpn_system(Path(old['release']),old['platform'])
                except BaseException as restore_error:
                    raise RuntimeError(f'TVPN setup failed and the previous protected backend could not be restored: {restore_error}') from restore_error
            shutil.rmtree(release,ignore_errors=True)
            raise
        print(json.dumps({'installed':state['version'],'complete':state['complete'],'unsupported':state['unsupported'],'prefix':str(prefix)},ensure_ascii=False))
        return state


def release_manifest():
    # Stable channel is the default; preview installs opt in through prefix/channel.
    return latest_suite_manifest(preview=os.environ.get('TTOOLS_CHANNEL')=='preview')

def update(prefix,force=False,automatic=False,remote=None):
    prefix=prefix_path(prefix)
    state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
    if (prefix/'channel').is_file():
        os.environ['TTOOLS_CHANNEL']=(prefix/'channel').read_text(encoding='utf-8').strip()
    stamp=prefix/'update-check.json'
    if automatic and stamp.is_file():
        cached=json.loads(stamp.read_text(encoding='utf-8'))
        retry_after=900 if cached.get('status')=='unavailable' else 21600
        if time.time()-cached.get('checked',0)<retry_after:return False
    with locked(prefix):
        remote=remote or release_manifest()
        if remote.get('schema_version') not in (1,2) or remote.get('app_id')!='ttools':raise ValueError('Invalid update manifest')
        remote_commit=remote.get('source_commit')
        if remote.get('schema_version')==2 and not valid_source_commit(remote_commit):
            raise ValueError('Invalid suite source commit')
        if remote_commit is not None and not valid_source_commit(remote_commit):
            raise ValueError('Invalid suite source commit')
        atomic_json(stamp,{'checked':time.time(),'version':remote['version']})
        if remote['version']==state['version']:
            return False
        # A release cannot silently downgrade an installed version.
        import re
        if version_key(remote['version'])<=version_key(state['version']):return False
        item=next((x for x in remote['artifacts'] if x['platform']==state['platform']),None)
        if not item:raise ValueError('No update for this OS/architecture')
        expected=item.get('sha256','')
        if not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('Invalid artifact checksum')
        with tempfile.TemporaryDirectory(prefix='ttools-update-') as folder:
            folder=Path(folder);archive=folder/'suite.zip'
            fetch(item['url'],archive)
            if digest(archive)!=expected:raise ValueError('Update SHA-256 mismatch')
            extract_zip(archive,folder/'unpacked')
            bundle=folder/'unpacked/ttools'
            manifest=verify_bundle(bundle)
            if manifest['version']!=remote['version'] or manifest['platform']!=state['platform']:
                raise ValueError('Update metadata mismatch')
            if remote_commit is not None and manifest.get('source_commit')!=remote_commit:
                raise ValueError('Update source commit mismatch')
            # Installation uses a fresh process after releasing the suite lock.
            pending=prefix/'pending'
            candidate=prefix/('.pending-'+str(time.time_ns()))
            try:
                shutil.copytree(bundle,candidate)
                if pending.exists():shutil.rmtree(pending)
                candidate.rename(pending)
            except BaseException:
                shutil.rmtree(candidate,ignore_errors=True)
                raise
    options=state['options']
    components=list(options['components'])
    if (state.get('platform')=='linux-x86_64'
            and set(components)=={'tspotify','ttelegram','tthings','tvpn'}):
        # Existing full-suite installs receive newly added default apps. Custom
        # component selections remain intact; unsupported apps are filtered by plan().
        components=list(APP_IDS)
    # Run the new installer so future schema/installer changes are honored.
    argv=[sys.executable,str(prefix/'pending/installer.py'),'--prefix',str(prefix),
          '--components',','.join(components)]
    if options['allow_partial']:argv.append('--allow-partial')
    if options['defer_system']:argv.append('--defer-system')
    if not options['shortcuts']:argv.append('--no-shortcuts')
    try:
        run(argv)
    finally:
        # The installer has copied verified bytes into releases before it
        # exits. Keep neither a stale verified package nor a failed candidate
        # in the staging slot after the process boundary.
        shutil.rmtree(prefix/'pending',ignore_errors=True)
    return True


def rollback(prefix):
    prefix=prefix_path(prefix)
    with locked(prefix):
        state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
        previous=state.get('previous')
        if not previous:raise RuntimeError('No previous suite release')
        active_release=_validate_release_state(prefix,state)
        previous_release=_validate_release_state(prefix,previous)
        current_options=state.get('options',{})
        previous_options=previous.get('options',{})
        current_tvpn='tvpn' in current_options.get('components',[])
        previous_tvpn='tvpn' in previous_options.get('components',[])
        current_system=current_tvpn and not current_options.get('defer_system',False)
        previous_system=previous_tvpn and not previous_options.get('defer_system',False)
        if current_system and not previous_tvpn:
            raise RuntimeError('Cannot roll back TVPN system files: the previous suite has no TVPN package')
        if current_system and previous_tvpn and not previous_system:
            raise RuntimeError('Cannot safely restore TVPN: the previous suite deferred system setup')
        stop_previous_background_apps(state)
        if previous_system:
            configure_tvpn_system(previous_release,previous['platform'])
        try:
            atomic_json(prefix/'state.json',previous)
        except BaseException:
            if previous_system and current_system:
                try:configure_tvpn_system(active_release,state['platform'])
                except BaseException as restore_error:
                    raise RuntimeError(f'Suite state rollback failed and the active TVPN backend could not be restored: {restore_error}') from restore_error
            raise
        print('Previous suite activated; user data preserved.')


def wait_process(child):
    """Forward termination; reap outside the signal handler to avoid Popen lock reentry."""
    previous={}
    requested=None
    def finish(signum,frame):
        nonlocal requested
        if requested is None:
            requested=signum
            if child.poll() is None:
                try:child.send_signal(signum)
                except ProcessLookupError:pass
    if os.name=='posix':
        for sig in (signal.SIGTERM,signal.SIGHUP):
            previous[sig]=signal.signal(sig,finish)
    try:
        while True:
            try:
                result=child.wait()
                if requested is not None:raise SystemExit(128+requested)
                return result
            except KeyboardInterrupt:continue
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


def launch_installed(prefix,args):
    configure_text_io()
    prefix=prefix_path(prefix)
    if args and args[0] in ('--update','--rollback','--status'):
        if args[0]=='--update':update(prefix,force=True)
        elif args[0]=='--rollback':rollback(prefix)
        else:print((prefix/'state.json').read_text(encoding='utf-8'))
        return 0
    is_app=len(args)>=2 and args[0]=='--app'
    update_commands=('--list','--check-updates','--import','--help')
    should_check=(not any(a in args for a in update_commands)
                  and os.environ.get('TTOOLS_AUTOUPDATE','1')!='0')
    if should_check:
        try:
            if sys.platform=='darwin' and sys.stdin.isatty() and sys.stdout.isatty():
                stamp=prefix/'update-check.json'
                cached=json.loads(stamp.read_text(encoding='utf-8')) if stamp.is_file() else {}
                retry_after=900 if cached.get('status')=='unavailable' else 21600
                due=time.time()-cached.get('checked',0)>=retry_after
                if due:
                    state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
                    if (prefix/'channel').is_file():
                        os.environ['TTOOLS_CHANNEL']=(prefix/'channel').read_text(encoding='utf-8').strip()
                    remote=release_manifest()
                    if remote.get('schema_version')!=1 or remote.get('app_id')!='ttools':
                        raise ValueError('Invalid suite update manifest')
                    atomic_json(stamp,{'checked':time.time(),'version':remote['version']})
                    if version_key(remote['version'])>version_key(state['version']):
                        print(f"\nttools {remote['version']} доступен (установлена версия {state['version']}).")
                        answer=input('Обновить сейчас? [д/Н] ').strip().casefold()
                        if answer in ('д','да','y','yes') and update(prefix,force=True,remote=remote):
                            _reexec(prefix,args)
            elif update(prefix,automatic=True):
                _reexec(prefix,args)
        except Exception as error:
            atomic_json(prefix/'update-error.json',{'time':time.time(),'error':str(error)})
            atomic_json(prefix/'update-check.json',{'checked':time.time(),'status':'unavailable'})
            # Network/dependency errors never prevent launching the installed version.
    with locked(prefix):
        state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
        release=Path(state['release'])
        os.environ['TTOOLS_CATALOG']=str(release/'apps.local.json')
        os.environ['TTOOLS_PREFIX']=str(prefix)
        if is_app:
            apps=json.loads((release/'apps.local.json').read_text(encoding='utf-8'))['apps']
            app=next((a for a in apps if a['id']==args[1]),None)
            if not app:raise RuntimeError('Application not installed: '+args[1])
            env=dict(os.environ,**app.get('env',{}))
            child=subprocess.Popen([*app['command'],*args[2:]],env=env)
            return wait_process(child)
        # Use the active release interpreter (windows-curses lives in its venv).
        env=dict(os.environ,PYTHONPATH=str(release))
        child=subprocess.Popen([state['python'],'-m','ttools',*args],env=env)
        return wait_process(child)


def main(argv=None):
    configure_text_io()
    parser=argparse.ArgumentParser(description='ttools suite install-only')
    parser.add_argument('--prefix')
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--components',default=None)
    parser.add_argument('--allow-partial',action='store_true')
    parser.add_argument('--defer-system',action='store_true',help='Stage VPN without privileged network setup; VPN will not be ready')
    parser.add_argument('--no-shortcuts',action='store_true')
    parser.add_argument('--plan',action='store_true')
    args=parser.parse_args(argv)
    if args.components is None:
        # Default excludes components with no native package for this platform.
        selected=tuple(default_components(platform_id()))
    else:
        selected=tuple(x for x in args.components.split(',') if x)
    if not selected:parser.error('At least one component is required')
    try:
        if args.plan:
            print(json.dumps(plan(args.bundle,platform_id(),selected,args.allow_partial),ensure_ascii=False,indent=2))
        else:
            install(args.bundle,prefix_path(args.prefix),selected,args.allow_partial,args.defer_system,not args.no_shortcuts)
        return 0
    except (OSError,RuntimeError,ValueError,subprocess.CalledProcessError) as error:
        print('ttools: '+str(error),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())


def _reexec(prefix,args):
    """Re-execute runner.py after an in-place update; Windows-safe."""
    runner=str(Path(prefix).resolve()/'runner.py')
    argv=[sys.executable,runner,*args]
    if os.name=='nt':
        # os.execv on Windows cannot reliably replace the current process; spawn
        # a fresh one and propagate its status after releasing our handles.
        raise SystemExit(subprocess.call(argv))
    os.execv(sys.executable,argv)
