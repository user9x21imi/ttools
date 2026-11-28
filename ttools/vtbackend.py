"""Small VT terminal backend for TTools curses-style views (Windows and POSIX).

All text and SIXEL share one byte stream; no Win32 screen-buffer writes.  The
Windows Console API always writes an explicit background attribute per cell, so
PDCurses turns ``-1`` (default) backgrounds into palette index 0 and paints an
opaque rectangle over a transparent/acrylic Windows Terminal.  Direct VT only
emits a background SGR when a real background was requested; untouched cells
keep the terminal's own (possibly transparent) background.

Only the curses API used by TTools applications is implemented.  Derived from
the ttelegram native backend so behaviour stays consistent across components.
"""
import codecs,collections,io,os,re,select,shutil,sys,threading,time,unicodedata
class error(Exception):pass
A_NORMAL=0;A_BOLD=1<<20;A_DIM=1<<21;A_REVERSE=1<<22;A_STANDOUT=A_REVERSE;A_UNDERLINE=1<<23;A_BLINK=1<<24;A_INVIS=1<<25
COLOR_BLACK=0;COLOR_RED=1;COLOR_GREEN=2;COLOR_YELLOW=3;COLOR_BLUE=4;COLOR_MAGENTA=5;COLOR_CYAN=6;COLOR_WHITE=7
COLORS=256;COLOR_PAIRS=65536
KEY_DOWN=258;KEY_UP=259;KEY_LEFT=260;KEY_RIGHT=261;KEY_HOME=262;KEY_BACKSPACE=263;KEY_DC=330;KEY_NPAGE=338;KEY_PPAGE=339;KEY_ENTER=343;KEY_END=360;KEY_MOUSE=409;KEY_RESIZE=410
for _i in range(1,25):globals()['KEY_F'+str(_i)]=264+_i
BUTTON1_PRESSED=1;BUTTON1_CLICKED=2;BUTTON1_DOUBLE_CLICKED=4;BUTTON1_RELEASED=8
BUTTON2_PRESSED=16;BUTTON2_RELEASED=32;BUTTON3_PRESSED=64;BUTTON3_RELEASED=128
BUTTON4_PRESSED=256;BUTTON5_PRESSED=512;ALL_MOUSE_EVENTS=0xffff
REPORT_MOUSE_POSITION=0x4000
_pairs={0:(-1,-1)};_colors={};_keys=collections.deque();_mouse=None;_root=None;_size=(24,80);_cells=(8,16);_sixel=None;_active=False;_saved=None;_out_original=None;_esc_delay=.025
_lock=threading.RLock();_decoder=codecs.getincrementaldecoder('utf-8')('replace')

def _emit(text):
    with _lock:sys.stdout.write(text);sys.stdout.flush()

def _dimensions():
    """Get terminal dimensions using multiple fallback methods.
    
    Priority order:
    1. os.get_terminal_size() on stdin/stdout/stderr
    2. Windows Console API (GetConsoleScreenBufferInfo) on stdout
    3. COLUMNS/LINES environment variables
    4. Fallback to (24, 80)
    """
    # Try os.get_terminal_size on all standard file descriptors
    for fd in (0, 1, 2):
        try:
            size = os.get_terminal_size(fd)
            if size.lines > 0 and size.columns > 0:
                return max(4, size.lines), max(12, size.columns)
        except OSError:
            pass
    
    # On Windows, try Console API for actual viewport size
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            
            class COORD(ctypes.Structure):
                _fields_ = [('X', wintypes.SHORT), ('Y', wintypes.SHORT)]
            class SMALL_RECT(ctypes.Structure):
                _fields_ = [('Left', wintypes.SHORT), ('Top', wintypes.SHORT),
                            ('Right', wintypes.SHORT), ('Bottom', wintypes.SHORT)]
            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [('dwSize', COORD),
                            ('dwCursorPosition', COORD),
                            ('wAttributes', wintypes.WORD),
                            ('srWindow', SMALL_RECT),
                            ('dwMaximumWindowSize', COORD)]
            
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(CONSOLE_SCREEN_BUFFER_INFO)]
            kernel.GetConsoleScreenBufferInfo.restype = wintypes.BOOL
            
            # Try stdout handle (-11) first as it's typically connected to the console in Windows Terminal
            handle = kernel.GetStdHandle(-11)
            if handle and handle != wintypes.HANDLE(-1).value:
                csbi = CONSOLE_SCREEN_BUFFER_INFO()
                if kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi)):
                    width = csbi.srWindow.Right - csbi.srWindow.Left + 1
                    height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                    if width > 0 and height > 0:
                        return max(4, height), max(12, width)
        except Exception:
            pass
    
    # Check environment variables
    try:
        cols = int(os.environ.get('COLUMNS', '0'))
        lines = int(os.environ.get('LINES', '0'))
        if cols > 0 and lines > 0:
            return max(4, lines), max(12, cols)
    except ValueError:
        pass
    
    return (24, 80)
def get_cell_size():return _cells
def supports_sixel():return _sixel
def color_pair(number):return number<<8
def init_pair(number,fg,bg):_pairs[number]=(fg,bg)
def init_color(number,r,g,b):_colors[number]=(round(r*255/1000),round(g*255/1000),round(b*255/1000))
def color_content(number):return tuple(round(x*1000/255) for x in _colors.get(number,(255,255,255)))
def can_change_color():return True
def has_colors():return True
def start_color():pass
def use_default_colors():pass
def set_escdelay(ms):
    global _esc_delay
    _esc_delay=max(.001,ms/1000)
def _sgr(attr):
    fg,bg=_pairs.get((attr>>8)&0xfff,(-1,-1));parts=['0']
    for flag,code in ((A_BOLD,'1'),(A_DIM,'2'),(A_REVERSE,'7'),(A_UNDERLINE,'4'),(A_BLINK,'5'),(A_INVIS,'8')):
        if attr&flag:parts.append(code)
    for number,base in ((fg,38),(bg,48)):
        if number<0:continue
        if number in _colors:parts.extend([str(base),'2',*map(str,_colors[number])])
        else:parts.extend([str(base),'5',str(number)])
    return '\x1b['+';'.join(parts)+'m'
def _width(char):
    if unicodedata.combining(char):return 0
    return 2 if unicodedata.east_asian_width(char) in ('W','F') else 1

class window:
    def __init__(self,h,w,y=0,x=0):
        self.h=max(1,h);self.w=max(1,w);self.y=y;self.x=x;self.row=0;self.col=0;self.attr=0;self.wait=-1;self.leave=False;self.erase()
    def getmaxyx(self):return self.h,self.w
    def getbegyx(self):return self.y,self.x
    def getyx(self):return self.row,self.col
    def erase(self):self.grid=[[(' ',0) for _ in range(self.w)] for _ in range(self.h)];self.dirty=set(range(self.h));self.row=self.col=0
    clear=erase
    def addstr(self,*args):
        if len(args)==1:y,x,text,attr=self.row,self.col,args[0],self.attr
        elif len(args)==2:y,x,text,attr=self.row,self.col,args[0],args[1]
        else:y,x,text=args[:3];attr=args[3] if len(args)>3 else self.attr
        if isinstance(text,bytes):text=text.decode('utf-8','replace')
        for char in str(text):
            if char=='\n':y+=1;x=0;continue
            if char=='\r':x=0;continue
            width=_width(char)
            if width==0:
                if 0<=y<self.h and 0<x<=self.w:
                    old,old_attr=self.grid[y][x-1]
                    if old is not None:self.grid[y][x-1]=(old+char,old_attr);self.dirty.add(y)
                continue
            if x+width>self.w:y+=1;x=0
            if 0<=y<self.h and 0<=x<self.w:
                self.grid[y][x]=(char,attr)
                if width==2 and x+1<self.w:self.grid[y][x+1]=(None,attr)
                self.dirty.add(y)
            x+=width
            if x>=self.w:y+=1;x=0
        self.row=min(self.h-1,max(0,y));self.col=min(self.w-1,max(0,x))
    def addnstr(self,y,x,text,n,attr=0):self.addstr(y,x,text[:max(0,n)],attr)
    insstr=addstr
    def move(self,y,x):self.row=max(0,min(self.h-1,y));self.col=max(0,min(self.w-1,x))
    def resize(self,h,w):self.h=max(1,h);self.w=max(1,w);self.erase()
    def mvwin(self,y,x):self.y=y;self.x=x;self.redrawwin()
    def subwin(self,h,w,y,x):return window(h,w,y,x)
    derwin=subwin
    def hline(self,y,x,char,n):self.addstr(y,x,(chr(char) if isinstance(char,int) else char)*max(0,n),self.attr)
    def vline(self,y,x,char,n):
        for row in range(y,min(self.h,y+n)):self.addstr(row,x,chr(char) if isinstance(char,int) else char,self.attr)
    def keypad(self,value):pass
    def scrollok(self,value):pass
    def leaveok(self,value):self.leave=value
    def clearok(self,value):
        if value:self.redrawwin()
    def redrawwin(self):self.dirty.update(range(self.h))
    touchwin=redrawwin
    def timeout(self,ms):self.wait=ms
    def nodelay(self,value):self.wait=0 if value else -1
    def attrset(self,value):self.attr=value
    def bkgd(self,char=' ',attr=0):self.attr=attr
    def refresh(self):
        if not _active:return
        output=[]
        for row in sorted(self.dirty):
            output.append(f'\x1b[{self.y+row+1};{self.x+1}H');active=None
            for char,attr in self.grid[row]:
                if char is None:continue
                if attr!=active:output.append(_sgr(attr));active=attr
                output.append(char)
        self.dirty.clear()
        if output:output.append('\x1b[0m');_emit(''.join(output))
    noutrefresh=refresh
    def get_wch(self,*position):
        if position:self.move(*position)
        if self.dirty:self.refresh()
        if position and not self.leave:_emit(f'\x1b[{self.y+self.row+1};{self.x+self.col+1}H')
        return _get_key(self.wait)
    def getch(self,*position):
        try:value=self.get_wch(*position)
        except error:return -1
        return ord(value) if isinstance(value,str) else value

_KEYS={'\x1b[A':KEY_UP,'\x1b[B':KEY_DOWN,'\x1b[C':KEY_RIGHT,'\x1b[D':KEY_LEFT,'\x1bOA':KEY_UP,'\x1bOB':KEY_DOWN,'\x1bOC':KEY_RIGHT,'\x1bOD':KEY_LEFT,'\x1b[H':KEY_HOME,'\x1bOH':KEY_HOME,'\x1b[F':KEY_END,'\x1bOF':KEY_END,'\x1b[1~':KEY_HOME,'\x1b[4~':KEY_END,'\x1b[7~':KEY_HOME,'\x1b[8~':KEY_END,'\x1b[3~':KEY_DC,'\x1b[5~':KEY_PPAGE,'\x1b[6~':KEY_NPAGE,'\x1bOP':KEY_F1,'\x1bOQ':KEY_F2,'\x1bOR':KEY_F3,'\x1bOS':KEY_F4}
for _number,_code in enumerate((11,12,13,14,15,17,18,19,20,21,23,24),1):_KEYS[f'\x1b[{_code}~']=globals()['KEY_F'+str(_number)]
def _read_char(deadline):
    if _keys:return _keys.popleft()
    if os.name=='nt':
        import msvcrt
        while not msvcrt.kbhit():
            if deadline is not None and time.monotonic()>=deadline:return None
            time.sleep(.005)
        char=msvcrt.getwch()
        if char in ('\0','\xe0'):
            second=msvcrt.getwch();return {'H':KEY_UP,'P':KEY_DOWN,'K':KEY_LEFT,'M':KEY_RIGHT,'G':KEY_HOME,'O':KEY_END,'S':KEY_DC,'I':KEY_PPAGE,'Q':KEY_NPAGE,';':KEY_F1,'>':KEY_F4,'A':KEY_F7}.get(second,0)
        if 0xD800<=ord(char)<=0xDBFF:
            following=msvcrt.getwch();return (char+following).encode('utf-16','surrogatepass').decode('utf-16')
        return char
    timeout=None if deadline is None else max(0,deadline-time.monotonic())
    if not select.select([0],[],[],timeout)[0]:return None
    data=os.read(0,4096)
    if not data:return None
    text=_decoder.decode(data)
    if not text:return _read_char(deadline)
    _keys.extend(text[1:]);return text[0]
def _get_key(wait):
    global _size,LINES,COLS,_cells,_sixel,_mouse
    deadline=None if wait<0 else time.monotonic()+wait/1000
    while True:
        size=_dimensions()
        if size!=_size:
            _size=size;LINES,COLS=size
            if _root:_root.resize(*size)
            return KEY_RESIZE
        char=_read_char(deadline)
        if char is None:raise error('timeout')
        if char!='\x1b':return KEY_BACKSPACE if char in ('\x7f','\b') else char
        tail='';escape_deadline=time.monotonic()+_esc_delay
        while len(tail)<128:
            next_char=_read_char(escape_deadline)
            if next_char is None:break
            if not isinstance(next_char,str):_keys.appendleft(next_char);break
            tail+=next_char
            if len(tail)>1 and (tail[-1].isalpha() or tail[-1]=='~'):break
            if tail[0] not in ('[','O'):break
        sequence='\x1b'+tail
        if sequence in _KEYS:return _KEYS[sequence]
        match=re.fullmatch(r'\[6;(\d+);(\d+)t',tail)
        if match:
            changed=_cells!=(int(match[2]),int(match[1]));_cells=(int(match[2]),int(match[1]))
            if changed:return KEY_RESIZE
            continue
        if tail.startswith('[?') and tail.endswith('c'):
            _sixel='4' in tail[2:-1].split(';');continue
        mouse=re.fullmatch(r'\[<(\d+);(\d+);(\d+)([Mm])',tail)
        if mouse:
            button,x,y=int(mouse[1]),int(mouse[2])-1,int(mouse[3])-1
            state=BUTTON4_PRESSED if button&64 and not button&1 else BUTTON5_PRESSED if button&64 else BUTTON1_PRESSED if mouse[4]=='M' and button&3==0 else 0
            _mouse=(0,x,y,0,state);return KEY_MOUSE
        _keys.extendleft(reversed(tail));return '\x1b'

def newwin(h,w,y=0,x=0):return window(h,w,y,x)
def _apply_console_modes():
    """(Re)enter the VT mode used by this backend."""
    if os.name=='nt':
        kernel,modes=_saved
        for handle,mode in modes:
            wanted=(mode|0x0200|0x0080)&~(0x0002|0x0004|0x0040) if handle==modes[0][0] else mode|0x0004
            if not kernel.SetConsoleMode(handle,wanted):raise error('Cannot enable VT console mode')
        kernel.SetConsoleOutputCP(65001)
    else:
        import tty
        tty.setraw(0)

def _restore_console_modes():
    if os.name=='nt':
        kernel,modes=_saved
        for handle,mode in modes:kernel.SetConsoleMode(handle,mode)
    else:
        import termios
        termios.tcsetattr(0,termios.TCSANOW,_saved)

def initscr():
    global _root,_size,LINES,COLS,_saved,_active,_out_original
    if _root is not None:
        if not _active:reset_prog_mode()
        return _root
    if os.name=='nt':
        import ctypes,msvcrt
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetStdHandle.restype=wintypes.HANDLE
        kernel.GetStdHandle.argtypes=[wintypes.DWORD]
        kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        modes=[]
        for kind in (-10,-11):
            handle=kernel.GetStdHandle(kind);mode=wintypes.DWORD()
            if not kernel.GetConsoleMode(handle,ctypes.byref(mode)):raise error('An interactive Windows Terminal console is required')
            modes.append((handle,mode.value))
        _saved=(kernel,modes);msvcrt.setmode(1,os.O_BINARY)
        _out_original=sys.stdout;sys.stdout=io.TextIOWrapper(io.FileIO(1,'w',closefd=False),encoding='utf-8',write_through=True)
    else:
        import termios
        _saved=termios.tcgetattr(0)
    _apply_console_modes()
    _size=_dimensions();LINES,COLS=_size;_root=window(*_size);_active=True
    _emit('\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[16t\x1b[c')
    return _root

def endwin():
    """Suspend the backend.  The root window survives so a child can be launched."""
    global _active
    if not _active:return
    _emit('\x1b[0m\x1b[?1000l\x1b[?1006l\x1b[?2004l\x1b[?25h\x1b[?1049l')
    _restore_console_modes()
    _active=False

def reset_prog_mode():
    """Restore the backend after a child process returned the terminal."""
    global _active
    if _active or _root is None:return
    _apply_console_modes()
    _emit('\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[16t\x1b[c')
    _root.erase();_active=True

def wrapper(callback,*args,**kwargs):
    screen=initscr()
    try:return callback(screen,*args,**kwargs)
    finally:endwin()
def curs_set(value):_emit('\x1b[?25h' if value else '\x1b[?25l')
def mousemask(value):_emit('\x1b[?1000h\x1b[?1006h' if value else '\x1b[?1000l\x1b[?1006l');return value,0
def mouseinterval(value):pass
def raw():pass
def noraw():pass
def flushinp():_keys.clear()
def def_prog_mode():
    """The backend already saved console modes in initscr(); nothing else to do."""
    pass
def getmouse():
    if _mouse is None:raise error('no mouse event')
    return _mouse
def ungetch(value):_keys.appendleft(chr(value) if isinstance(value,int) and value<256 else value)
unget_wch=ungetch
def unctrl(value):
    if isinstance(value,str):value=ord(value)
    return ('^'+chr(value+64)).encode() if 0<=value<32 else b'^?' if value==127 else chr(value).encode()
def noecho():pass
def echo():pass
def cbreak():pass
def nocbreak():pass
def doupdate():pass
def getsyx():return (-1,-1)
LINES,COLS=_size


def usable():
    """True when a real console is attached and VT modes can be enabled."""
    if os.name!='nt':return True
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.restype=wintypes.HANDLE
    kernel.GetStdHandle.argtypes=[wintypes.DWORD]
    kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    for kind in (-10,-11):
        mode=wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(kind),ctypes.byref(mode)):return False
    return True

def prepare_console_output():
    """Enable ANSI and UTF-8 before the QR login and splash, preserving input."""
    if os.name!='nt':return
    import ctypes,msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.restype=wintypes.HANDLE
    kernel.GetStdHandle.argtypes=[wintypes.DWORD]
    kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    handle=kernel.GetStdHandle(-11);mode=wintypes.DWORD()
    if not kernel.GetConsoleMode(handle,ctypes.byref(mode)):raise error('Run Telegram inside Windows Terminal')
    if not kernel.SetConsoleMode(handle,mode.value|4):raise error('Cannot enable VT output')
    kernel.SetConsoleOutputCP(65001)
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
