"""Route global exit to the worker's save-and-exit handler, even inside overlays."""
import os,signal,subprocess,sys
from pathlib import Path
from runtime import ROOT,SOCKET,command

def worker_pid(root):
    pending=[root];seen=set()
    while pending:
        pid=pending.pop()
        if pid in seen:continue
        seen.add(pid)
        try:
            args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            if str(ROOT/'client.py').encode() in args and b'--worker' in args:return pid
            for task in Path(f'/proc/{pid}/task').glob('*'):
                try:pending.extend(map(int,task.joinpath('children').read_text().split()))
                except OSError:pass
        except OSError:pass
    return None

def main():
    result=subprocess.run(['tmux','-L',SOCKET,'display-message','-p','-t','telegram:0.0','#{pane_pid}'],capture_output=True,text=True)
    if result.returncode:return
    try:pid=worker_pid(int(result.stdout.strip()))
    except ValueError:return
    if '--restart' in sys.argv:
        restart_command=command(sys.executable,ROOT/'restart_client.py',pid or 0)
        subprocess.run(['tmux','-L',SOCKET,'respawn-pane','-k','-t','telegram:0.0',restart_command],check=True)
        return
    if pid is not None:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    else:subprocess.run(['tmux','-L',SOCKET,'send-keys','-t','telegram:0.0','C-q'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if __name__=='__main__':main()
