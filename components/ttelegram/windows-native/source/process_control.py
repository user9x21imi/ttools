"""Per-installation file IPC; stop is cooperative and never sends kill signals."""
import json,os,time,uuid
from pathlib import Path

def default_prefix():return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ttools/ttelegram'
def data_root():return Path(os.environ.get('TTELEGRAM_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ttools/ttelegram-data')
def lock(path,blocking=False):
    path.parent.mkdir(parents=True,exist_ok=True);file=path.open('a+b')
    if not path.stat().st_size:file.write(b'\0');file.flush()
    file.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(file.fileno(),msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(file.fileno(),fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
    except OSError:file.close();raise
    return file

def running(prefix):
    try:file=lock(prefix/'run/instance.lock')
    except OSError:return True
    file.close();return False

def stop(prefix,timeout=12):
    if not running(prefix):return
    state=json.loads((prefix/'run/process.json').read_text(encoding='utf-8'))
    flag=prefix/'run/stop.request';temp=flag.with_suffix('.tmp');temp.write_text(state['token'],encoding='utf-8');os.replace(temp,flag)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if not running(prefix):return
        time.sleep(.1)
    raise RuntimeError('The client did not finish its save-and-exit request; no update was applied')
