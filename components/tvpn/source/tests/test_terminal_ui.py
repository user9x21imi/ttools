"""Run the real curses app in a PTY with the network-free synthetic backend."""
import os
from pathlib import Path
import select
import signal
import struct
import sys
import time
import unittest

try:
    import fcntl
    import termios
    import pty
except ImportError:  # Windows has no fcntl/termios/pty; the suite skips below.
    fcntl = None
    termios = None
    pty = None

SOURCE=Path(__file__).resolve().parents[1]
LAUNCH=SOURCE/'launch.py'
PTY_SUPPORTED=os.name=='posix' and termios is not None and hasattr(termios,'TIOCSWINSZ')


@unittest.skipUnless(PTY_SUPPORTED,'PTY+curses integration is available on POSIX systems')
class CursesPtyTests(unittest.TestCase):
    def start(self,columns,rows,extra_env=None):
        pid,master=pty.fork()
        if pid==0:
            fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',rows,columns,0,0))
            env=dict(os.environ,TERM='xterm-256color',LC_ALL='C.UTF-8',
                     PYTHONIOENCODING='utf-8',TVPN_NO_MOTION='0',RISEUP_NO_UPDATE_CHECK='1')
            env.update(extra_env or {})
            os.execvpe(sys.executable,[sys.executable,str(LAUNCH),'--demo'],env)
        self.addCleanup(self.close,pid,master)
        self.resize(master,columns,rows)
        return pid,master

    @staticmethod
    def resize(master,columns,rows):
        fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,columns,0,0))

    @staticmethod
    def read_for(master,seconds):
        data=bytearray()
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],min(.1,deadline-time.monotonic()))
            if not ready:continue
            try:chunk=os.read(master,65536)
            except OSError:break
            if not chunk:break
            data.extend(chunk)
        return bytes(data)

    @classmethod
    def close(cls,pid,master):
        try:os.write(master,b'\x11')
        except OSError:pass
        deadline=time.monotonic()+3
        status=None
        while time.monotonic()<deadline:
            try:
                done,status=os.waitpid(pid,os.WNOHANG)
            except ChildProcessError:
                break
            if done:break
            cls.read_for(master,.1)
        else:
            # TERM runs the app's graceful handler; never kill the synthetic backend.
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:os.waitpid(pid,0)
            except ChildProcessError:pass
        try:os.close(master)
        except OSError:pass

    def test_actual_curses_draws_at_reference_sizes(self):
        for columns,rows in ((80,24),(120,40),(160,50)):
            with self.subTest(columns=columns,rows=rows):
                pid,master=self.start(columns,rows)
                capture=self.read_for(master,1.8)
                self.assertIn(b'TVPN',capture)
                self.assertIn(b'SIMULATED ROUTE',capture)
                self.assertIn(b'DOWNLOAD',capture)
                self.assertNotIn(b'Traceback',capture)
                self.close(pid,master)

    def test_keyboard_resize_region_log_stop_and_exit(self):
        pid,master=self.start(80,24)
        capture=bytearray(self.read_for(master,.8))
        self.resize(master,120,40)
        capture.extend(self.read_for(master,.35))
        os.write(master,b'r')
        capture.extend(self.read_for(master,.25))
        os.write(master,b'\x1bOB')  # xterm-256color application-cursor sequence for KEY_DOWN
        capture.extend(self.read_for(master,.35))
        os.write(master,b'\n')
        capture.extend(self.read_for(master,1.8))
        os.write(master,b'l')
        capture.extend(self.read_for(master,.2))
        capture.extend(self.read_for(master,.2))
        os.write(master,b'l')
        capture.extend(self.read_for(master,.2))
        os.write(master,b'\x13')
        capture.extend(self.read_for(master,.8))
        os.write(master,b'\x11')
        capture.extend(self.read_for(master,.7))
        self.close(pid,master)
        self.assertIn('ВЫБОР БЕСПЛАТНОГО РЕГИОНА'.encode(),capture)
        self.assertIn('Париж / FR'.encode(),capture)
        self.assertIn(b'no network state changed',capture)
        self.assertNotIn('DNS восстановлен'.encode(),capture)
        self.assertIn(b'EVENT LOG',capture)
        self.assertIn('ОТКЛЮЧЕНО'.encode(),capture)
        self.assertNotIn(b'Traceback',capture)

    def test_ctrl_c_stops_in_place_without_exiting_ui(self):
        pid,master=self.start(80,24)
        self.read_for(master,2.2)
        os.write(master,b'\x03')
        capture=self.read_for(master,1.5)
        done,_=os.waitpid(pid,os.WNOHANG)
        self.assertEqual(done,0,'Ctrl+C should stop the tunnel while keeping the panel open')
        self.assertIn('ОТКЛЮЧЕНО'.encode(),capture)
        os.write(master,b'\x11')
        self.read_for(master,.4)
        self.close(pid,master)

    def test_ctrl_q_exits_after_confirmed_cleanup(self):
        pid,master=self.start(80,24)
        capture=bytearray(self.read_for(master,2.0))
        self.assertIn(b'SIMULATED ROUTE',capture)
        os.write(master,b'\x11')
        capture.extend(self.read_for(master,1.5))
        done,_=os.waitpid(pid,os.WNOHANG)
        self.assertEqual(done,pid,'Ctrl+Q should close after the backend confirms cleanup')
        self.assertIn(b'no network state changed',capture)
        self.assertNotIn(b'Traceback',capture)

    def test_ctrl_q_keeps_error_visible_when_cleanup_fails(self):
        pid,master=self.start(80,24,{'TVPN_DEMO_CLEANUP_FAILURE':'1'})
        self.read_for(master,2.0)
        os.write(master,b'\x11')
        capture=self.read_for(master,.7)
        done,_=os.waitpid(pid,os.WNOHANG)
        self.assertEqual(done,0,'The panel should remain open when cleanup is unconfirmed')
        # curses diffs only the changed suffix; the leading О is already on screen.
        self.assertIn('ШИБКА'.encode(),capture)
        self.assertIn('состояние сети неизвестно'.encode(),capture)
        os.write(master,b'\x11')
        self.read_for(master,.4)
        self.close(pid,master)


if __name__=='__main__':unittest.main()
