import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import zipapp
import zipfile


def desktop_quote(path):
    return '"'+str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'


def install(with_hotkeys=False):
    home=Path.home()
    frozen=getattr(sys,'frozen',False)
    if os.name=='nt':
        target=Path(os.environ.get('LOCALAPPDATA',home/'AppData/Local'))/'tthings'
        target.mkdir(parents=True,exist_ok=True)
        exe=target/'tthings.exe' if frozen else target/'tthings.pyz'
    else:
        target=home/'.local/bin';target.mkdir(parents=True,exist_ok=True)
        exe=target/'tthings'
    if frozen:
        if Path(sys.executable).resolve()!=exe.resolve():
            temporary=exe.with_name(exe.name+'.new')
            shutil.copy2(sys.executable,temporary)
            os.replace(temporary,exe)
    elif Path(sys.argv[0]).is_file() and zipfile.is_zipfile(sys.argv[0]):
        if Path(sys.argv[0]).resolve()!=exe.resolve():shutil.copy2(sys.argv[0],exe)
    else:
        # A zipapp is an actual single-file application, not a pointer to this checkout.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='tthings-install-') as td:
            package=Path(td)/'tthings'
            shutil.copytree(Path(__file__).parent,package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            zipapp.create_archive(td,exe,interpreter='/usr/bin/env python3',main='tthings.__main__:main',compressed=True)
    if os.name!='nt':exe.chmod(0o755)
    cmd=([str(exe)] if frozen or os.name!='nt' else [sys.executable,str(exe)])
    if sys.platform.startswith('linux'):
        apps=home/'.local/share/applications';apps.mkdir(parents=True,exist_ok=True)
        (apps/'tthings.desktop').write_text('[Desktop Entry]\nType=Application\nName=tthings\nComment=Terminal playground\nExec='+desktop_quote(exe)+'\nTerminal=true\nIcon=utilities-terminal\nCategories=Utility;\n',encoding='utf-8')
        (apps/'tthings-region.desktop').write_text('[Desktop Entry]\nType=Application\nName=tthings — область\nExec='+desktop_quote(exe)+' --region\nTerminal=false\nIcon=preferences-desktop-screensaver\nCategories=Utility;\n'+('X-KDE-Shortcuts=Meta+Alt+G\n' if with_hotkeys else ''),encoding='utf-8')
        (apps/'tthings-region-snap.desktop').write_text('[Desktop Entry]\nType=Application\nName=tthings — область с привязкой\nExec='+desktop_quote(exe)+' --region --snap\nTerminal=false\nIcon=preferences-desktop-screensaver\nCategories=Utility;\n'+('X-KDE-Shortcuts=Meta+Ctrl+Alt+G\n' if with_hotkeys else ''),encoding='utf-8')
    elif sys.platform=='darwin':
        app=home/'Applications'/'tthings.command';app.parent.mkdir(parents=True,exist_ok=True)
        import shlex
        app.write_text('#!/bin/sh\nexec '+shlex.join(cmd)+' "$@"\n',encoding='utf-8');app.chmod(0o755)
    else:
        launcher=target/'tthings.cmd'
        import subprocess as sp
        launcher.write_text('@echo off\r\n'+sp.list2cmdline(cmd)+' %*\r\n',encoding='utf-8')
        # Add only the application's directory to the current user's PATH.
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
            try:old,kind=winreg.QueryValueEx(key,'Path')
            except FileNotFoundError:old,kind='',winreg.REG_EXPAND_SZ
            if str(target).casefold() not in [p.casefold() for p in old.split(';')]:
                winreg.SetValueEx(key,'Path',0,kind,old.rstrip(';')+';'+str(target))
        desktop=home/'Desktop'
        if desktop.exists():
            shortcut=desktop/'tthings.cmd';shutil.copy2(launcher,shortcut)
    print('Установлено:',exe)
    print('Запуск: tthings (в новом терминале), либо',exe)
    print('Выделение области:', ' '.join(cmd+['--region']))
    if with_hotkeys:enable_hotkey(cmd)
    else:print('Глобальные клавиши не изменялись. Для включения: --install --with-hotkeys')
    return exe


def enable_hotkey(cmd=None):
    from .app import invocation
    cmd=cmd or invocation()
    home=Path.home()
    if sys.platform.startswith('linux') and 'KDE' in os.environ.get('XDG_CURRENT_DESKTOP',''):
        # KGlobalAccel owns shortcuts on Wayland. Write only our own service group.
        writer=shutil.which('kwriteconfig6') or shutil.which('kwriteconfig5')
        if writer and (home/'.local/share/applications/tthings-region.desktop').exists():
            subprocess.run([writer,'--file','kglobalshortcutsrc','--group','services','--group','tthings-region.desktop','--key','_launch','Meta+Alt+G'],check=True)
            subprocess.run([writer,'--file','kglobalshortcutsrc','--group','services','--group','tthings-region-snap.desktop','--key','_launch','Meta+Ctrl+Alt+G'],check=True)
            print('KDE: Meta+Alt+G и Ctrl+Meta+Alt+G записаны. Если не сработало сразу — выйдите и войдите в сеанс.')
        else:
            print('KDE: назначьте Meta+Alt+G команде tthings --region в системных сочетаниях клавиш.')
    elif os.name=='nt':
        import subprocess as sp
        startup=Path(os.environ.get('APPDATA',home/'AppData/Roaming'))/'Microsoft/Windows/Start Menu/Programs/Startup'
        startup.mkdir(parents=True,exist_ok=True)
        command=sp.list2cmdline(cmd+['--hotkey']).replace('"','""')
        (startup/'tthings.vbs').write_text('CreateObject("WScript.Shell").Run "'+command+'", 0, False\r\n',encoding='utf-8')
        print('Win+Alt+G / Ctrl+Win+Alt+G: включатся при следующем входе. Сейчас: tthings --hotkey')
    elif sys.platform=='darwin':
        agents=home/'Library/LaunchAgents';agents.mkdir(parents=True,exist_ok=True)
        path=agents/'app.tthings.hotkey.plist'
        path.write_bytes(plistlib.dumps({'Label':'app.tthings.hotkey','ProgramArguments':cmd+['--hotkey'],'RunAtLoad':True}))
        print('Cmd+Option+G / Ctrl+Cmd+Option+G: включатся при следующем входе. Сейчас: tthings --hotkey')
    elif os.environ.get('XDG_SESSION_TYPE')!='wayland':
        import shlex
        auto=home/'.config/autostart';auto.mkdir(parents=True,exist_ok=True)
        (auto/'tthings-hotkey.desktop').write_text('[Desktop Entry]\nType=Application\nName=tthings hotkey\nExec='+shlex.join(cmd+['--hotkey'])+'\nTerminal=false\n',encoding='utf-8')
        print('X11: Meta+Alt+G / Ctrl+Meta+Alt+G включатся при следующем входе. Сейчас: tthings --hotkey')
    else:print('Wayland: назначьте Meta+Alt+G команде tthings --region в настройках рабочего стола.')
