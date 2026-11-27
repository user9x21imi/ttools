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
        from .konsole_title import is_konsole
        self.konsole=is_konsole();self.previous_tab_format=None

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
            kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
            kernel.SetConsoleMode.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            STD_OUTPUT_HANDLE=-11;STD_INPUT_HANDLE=-10
            ENABLE_PROCESSED_INPUT=0x1;ENABLE_LINE_INPUT=0x2;ENABLE_ECHO_INPUT=0x4
            ENABLE_EXTENDED_FLAGS=0x80;ENABLE_QUICK_EDIT_MODE=0x40
            ENABLE_VIRTUAL_TERMINAL_PROCESSING=0x4;ENABLE_VIRTUAL_TERMINAL_INPUT=0x200
            # Output: virtual-terminal processing. Input: cbreak-style, no echo,
            # no quick-edit, preserve processed input; restore exactly on stop.
            for channel,mask_set,mask_clear in (
                    (STD_OUTPUT_HANDLE,ENABLE_VIRTUAL_TERMINAL_PROCESSING,0),
                    (STD_INPUT_HANDLE,ENABLE_EXTENDED_FLAGS|ENABLE_VIRTUAL_TERMINAL_INPUT,ENABLE_LINE_INPUT|ENABLE_ECHO_INPUT|ENABLE_QUICK_EDIT_MODE)):
                try:
                    handle=kernel.GetStdHandle(channel)
                    mode=wintypes.DWORD()
                    if not handle or not kernel.GetConsoleMode(handle,ctypes.byref(mode)):
                        continue
                    original=mode.value
                    if channel==STD_INPUT_HANDLE:
                        new=(original|mask_set|ENABLE_PROCESSED_INPUT)&~mask_clear
                    else:
                        new=original|mask_set
                    self.win_modes.append((handle,original))
                    kernel.SetConsoleMode(handle,new)
                except (OSError,ValueError):
                    # Not a real console (redirected output); still emit VT codes.
                    pass
        else:
            import termios,tty
            self.old=termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        self.active=True
        if self.konsole:
            from .konsole_title import previous_tab_format
            self.previous_tab_format=previous_tab_format()
        self.write(ESC+'[22;0t')
        self.current_title=None
        self.set_title()
        self.write(ESC+'[?1049h'+ESC+'[?25l'+ESC+'[2J')

    def stop(self):
        if not self.active:return
        if self.konsole and self.previous_tab_format is not None:
            restored=''.join(c if c.isprintable() else ' ' for c in self.previous_tab_format)[:512]
            self.write(ESC+']30;'+restored+'\x07')
            self.previous_tab_format=None
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
            self.write(ESC+']0;'+label+'\x07'+(ESC+']30;%w\x07' if self.konsole else ''))
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
                return {'H':'up','P':'down','K':'left','M':'right','I':'pgup','Q':'pgdown','S':'delete','R':'f1',';':'f1'}.get(msvcrt.getwch(),'')
            if ch==ESC:
                # Windows Terminal with ENABLE_VIRTUAL_TERMINAL_INPUT sends VT
                # sequences; a bare ESC remains 'escape'.
                seq=ch
                while msvcrt.kbhit() and len(seq)<12:
                    seq+=msvcrt.getwch()
                return _vt_key(seq)
            return {'\r':'enter','\n':'enter','\x08':'backspace','\x7f':'backspace','\t':'tab'}.get(ch,ch)
        if select.select([sys.stdin],[],[],timeout)[0]:
            data=os.read(sys.stdin.fileno(),4096)
            if not data:raise EOFError
            self.buffer+=self.decoder.decode(data)
        if not self.buffer:return None
        sequences={'\x1b[A':'up','\x1b[B':'down','\x1b[C':'right','\x1b[D':'left',
                   '\x1b[5~':'pgup','\x1b[6~':'pgdown','\x1b[3~':'delete','\x1b[H':'home','\x1b[F':'end','\x1bOP':'f1','\x1bOQ':'f2','\x1b[12~':'f2',
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


def _vt_key(seq):
    table={'\x1b[A':'up','\x1b[B':'down','\x1b[C':'right','\x1b[D':'left','\x1b[5~':'pgup','\x1b[6~':'pgdown','\x1b[3~':'delete','\x1b[H':'home','\x1b[F':'end','\x1bOP':'f1','\x1bOQ':'f2','\x1bOA':'up','\x1bOB':'down','\x1bOC':'right','\x1bOD':'left','\x1b[12~':'f2'}
    if seq in table:return table[seq]
    return 'escape'