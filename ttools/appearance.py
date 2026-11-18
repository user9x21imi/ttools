"""Temporarily select the transparent Konsole profile for this session only."""
from contextlib import contextmanager
import os
import shutil
import subprocess

@contextmanager
def konsole_profile():
    command = shutil.which('qdbus6') or shutil.which('qdbus')
    service = os.environ.get('KONSOLE_DBUS_SERVICE')
    session = os.environ.get('KONSOLE_DBUS_SESSION')
    previous = None
    def call(method,*args):
        return subprocess.run([command,service,session,'org.kde.konsole.Session.'+method,*args],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
    try:
        if command and service and session:
            try:
                previous = call('profile')
                call('setProfile','ttools')
            except (OSError,subprocess.SubprocessError):
                pass
        yield
    finally:
        if previous:
            try:
                call('setProfile',previous)
            except (OSError,subprocess.SubprocessError):
                pass
