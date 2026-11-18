"""Exercise the shared VT frontend on POSIX; not a Windows host certification."""
import os,sys,time,json,subprocess,tempfile,threading,struct
from pathlib import Path
if os.name=='nt':raise SystemExit('Use run.cmd --demo on Windows; this PTY harness is for POSIX')
import pty,fcntl,termios
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='Telegram UI тест ') as folder:
    folder=Path(folder);master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',45,140,1120,720))
    code="import os,runpy;from pathlib import Path;import windows_bootstrap;windows_bootstrap.install(native_td=False,configure_paths=False);runpy.run_path(str(Path(os.environ['TEST_SOURCE'])/'demo_scenario.py'),init_globals={'demo_path':lambda name:Path(os.environ['TTELEGRAM_DEMO_DIR'])/name})"
    env=dict(os.environ,PYTHONPATH=str(root/'source'),TEST_SOURCE=str(root/'source'),TTELEGRAM_DEMO_DIR=str(folder),TERM='xterm-256color')
    process=subprocess.Popen([sys.executable,'-c',code],env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave);output=bytearray()
    def drain():
        while True:
            try:output.extend(os.read(master,65536))
            except OSError:return
    threading.Thread(target=drain,daemon=True).start()
    def state():
        try:return json.loads((folder/'tt-native-test-ready.json').read_text())
        except (ValueError,OSError):return {}
    def wait(predicate):
        until=time.monotonic()+12
        while time.monotonic()<until:
            value=state()
            if predicate(value):return value
            if process.poll() is not None:raise AssertionError('UI exited: '+output[-2000:].decode('utf-8','replace'))
            time.sleep(.05)
        raise AssertionError(value)
    def key(text):os.write(master,text.encode());time.sleep(.15)
    try:
        wait(lambda s:s.get('count')==2);key('\x1b[6;16;8t');key('\r');wait(lambda s:s.get('mode')=='messages')
        key('\x16');key('CAPTION');wait(lambda s:s.get('attachments',{}).get('chat:101') and s.get('buffer')=='CAPTION')
        key('\r');sent=wait(lambda s:s.get('current_id')==20001 and not s.get('pending') and s.get('buffer')=='')
        time.sleep(1);assert state()['frames']<=sent['frames']+1,'progress-only events repainted history'
        key('\x1b[A');wait(lambda s:s.get('current_id')!=20001 and not s.get('pending'))
        key('\x1b[B');wait(lambda s:s.get('current_id')==20001 and not s.get('pending'))
        key('\x0f');time.sleep(.3);key('\x1b');wait(lambda s:s.get('current_id')==20001 and not s.get('pending'))
        key('\x0c');wait(lambda s:s.get('mode')=='chats');key('\r');wait(lambda s:s.get('mode')=='messages')
        key('SAVED DRAFT');wait(lambda s:s.get('buffer')=='SAVED DRAFT');key('\x11');process.wait(timeout=5)
        assert process.returncode==0,output[-3000:]
        assert '\x1bP0;0q' in output.decode('utf-8','replace'),'no SIXEL graphics emitted'
        assert (folder/'tt-native-test-session.json').is_file()
        print('PASS: chat navigation, paste + caption, fake photo send, 100 progress updates without history repaint, scroll, settings return, chat list, draft save, Ctrl+Q, SIXEL output')
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        os.close(master)
