import codecs
import os
import select
import shutil
import sys
import time

ESC='\x1b'

class Terminal:
    def __init__(self):
        self.active=False
        self.old=None
        self.buffer=''
        self.escape_since=None
        self.decoder=codecs.getincrementaldecoder('utf-8')('replace')
        self.win_modes=[]
        self.current_title=None

    def __enter__(self):
        self.start()
        return self

    def start(self):
        if self.active:return
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.windll.kernel32
            kernel.GetStdHandle.restype=wintypes.HANDLE
            for channel,flags in ((-11,4),(-10,0x200)):
                handle=kernel.GetStdHandle(channel)
                mode=wintypes.DWORD()
                if kernel.GetConsoleMode(handle,ctypes.byref(mode)):
                    self.win_modes.append((handle,mode.value))
                    # Disable line input, echo and quick-edit, preserve processed input.
                    new=mode.value|flags if channel==-11 else (mode.value|0x200|0x80)&~(0x2|0x4|0x40)
                    kernel.SetConsoleMode(handle,new)
        else:
            import termios,tty
            self.old=termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        self.active=True
        self.write(ESC+'[22;0t')
        self.current_title=None
        self.set_title()
        self.write(ESC+'[?1049h'+ESC+'[?25l'+ESC+'[2J')

    def stop(self):
        if not self.active:return
        self.write(ESC+'[0m'+ESC+'[?25h'+ESC+'[?1049l'+ESC+'[23;0t')
        self.current_title=None
        if os.name=='nt':
            import ctypes
            for handle,mode in self.win_modes:ctypes.windll.kernel32.SetConsoleMode(handle,mode)
            self.win_modes=[]
        elif self.old:
            import termios
            termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,self.old)
        self.active=False

    def __exit__(self,*args):self.stop()

    @staticmethod
    def write(value):
        sys.stdout.write(value)
        sys.stdout.flush()

    def set_title(self,function=None):
        label='tthings'+(' — '+function if function else '')
        label=''.join(char if char.isprintable() else ' ' for char in label)[:160]
        if label!=self.current_title:
            self.write(ESC+']0;'+label+'\x07')
            self.current_title=label

    @staticmethod
    def size():
        s=shutil.get_terminal_size((100,30))
        return max(1,s.columns-1),max(1,s.lines)

    def read(self,timeout=.03):
        if os.name=='nt':
            import msvcrt
            until=time.monotonic()+timeout
            while not msvcrt.kbhit():
                if time.monotonic()>=until:return None
                time.sleep(.005)
            ch=msvcrt.getwch()
            if ch in ('\x00','\xe0'):
                return {'H':'up','P':'down','K':'left','M':'right','I':'pgup','Q':'pgdown'}.get(msvcrt.getwch(),'')
            return {'\r':'enter','\x08':'backspace','\x1b':'escape','\t':'tab'}.get(ch,ch)
        if select.select([sys.stdin],[],[],timeout)[0]:
            data=os.read(sys.stdin.fileno(),4096)
            if not data:raise EOFError
            self.buffer+=self.decoder.decode(data)
        if not self.buffer:return None
        sequences={'\x1b[A':'up','\x1b[B':'down','\x1b[C':'right','\x1b[D':'left',
                   '\x1b[5~':'pgup','\x1b[6~':'pgdown','\x1bOP':'f1','\x1bOQ':'f2','\x1b[12~':'f2',
                   '\x1bOA':'up','\x1bOB':'down','\x1bOC':'right','\x1bOD':'left'}
        for seq,name in sequences.items():
            if self.buffer.startswith(seq):
                self.buffer=self.buffer[len(seq):]; self.escape_since=None
                return name
        if self.buffer.startswith(ESC):
            if self.escape_since is None:self.escape_since=time.monotonic()
            if any(seq.startswith(self.buffer) for seq in sequences) and time.monotonic()-self.escape_since<.06:return None
            self.buffer=self.buffer[1:]; self.escape_since=None
            return 'escape'
        ch,self.buffer=self.buffer[0],self.buffer[1:]
        return {'\r':'enter','\n':'enter','\x7f':'backspace','\x08':'backspace','\t':'tab'}.get(ch,ch)

    def draw(self,frame):
        parts=[ESC+'[H']
        color=None
        for y,row in enumerate(frame.cells):
            if y:parts.append(ESC+f'[{y+1};1H')
            for char,c in row:
                if c!=color:
                    r,g,b=(int(c[i:i+2],16) for i in (1,3,5))
                    parts.append(ESC+f'[38;2;{r};{g};{b}m');color=c
                parts.append(char)
            parts.append(ESC+'[K')
        parts.append(ESC+'[0m')
        self.write(''.join(parts))
