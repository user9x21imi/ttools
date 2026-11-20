"""Optional tab-format capture. OSC updates work without D-Bus or helpers."""
import configparser
import os
from pathlib import Path
import shutil
import subprocess


def is_konsole():
    return bool(os.environ.get('KONSOLE_VERSION') or os.environ.get('KONSOLE_DBUS_SESSION')) and not (os.environ.get('TMUX') or os.environ.get('STY'))


def previous_tab_format():
    service=os.environ.get('KONSOLE_DBUS_SERVICE');session=os.environ.get('KONSOLE_DBUS_SESSION')
    command=shutil.which('qdbus6') or shutil.which('qdbus')
    if service and session and command:
        try:
            result=subprocess.run([command,service,session,'org.kde.konsole.Session.tabTitleFormat','0'],capture_output=True,text=True,timeout=.4)
            if result.returncode==0 and result.stdout.strip():return result.stdout.rstrip('\n')
        except (OSError,subprocess.SubprocessError):pass
    # Without session-bus access, restore the configured profile's local format.
    config=configparser.ConfigParser(interpolation=None);config.optionxform=str
    try:
        config.read(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'konsolerc')
        profile=config.get('Desktop Entry','DefaultProfile',fallback='')
        roots=[Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))]+[Path(p) for p in os.environ.get('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':') if p]
        seen=set()
        while profile and profile not in seen:
            seen.add(profile);name=Path(profile).name
            file=next((root/'konsole'/name for root in roots if (root/'konsole'/name).is_file()),None)
            if file is None:break
            settings=configparser.ConfigParser(interpolation=None);settings.optionxform=str;settings.read(file)
            if settings.has_option('General','LocalTabTitleFormat'):return settings.get('General','LocalTabTitleFormat')
            profile=settings.get('General','Parent',fallback='')
    except (OSError,configparser.Error):pass
    return '%d : %n'
