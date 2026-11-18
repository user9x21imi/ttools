"""SIXEL rendered through tmux so images obey pane erasure and clipping."""
from functools import lru_cache
import array,fcntl,os,struct,subprocess,sys,termios,time,re,threading
from functools import wraps
from pathlib import Path
from PIL import Image,ImageOps


_cell_cache=(8,16)
_cell_time=0

def cell_pixels():
    global _cell_cache,_cell_time
    if time.monotonic()-_cell_time<.25:return _cell_cache
    if os.environ.get('TMUX'):
        try:
            result=subprocess.run(['tmux','display-message','-p','-t',os.environ['TMUX_PANE'],'#{window_cell_width} #{window_cell_height}'],capture_output=True,text=True,timeout=1)
            values=result.stdout.split()
            if len(values)==2 and all(int(value)>0 for value in values):
                _cell_cache=tuple(map(int,values));_cell_time=time.monotonic();return _cell_cache
        except (OSError,ValueError,subprocess.SubprocessError):pass
    try:
        rows,cols,x,y=struct.unpack('HHHH',fcntl.ioctl(sys.stdout.fileno(),termios.TIOCGWINSZ,b'\0'*8))
        if x and y and rows and cols:_cell_cache=(max(4,x//cols),max(8,y//rows))
    except (OSError,ValueError):pass
    _cell_time=time.monotonic();return _cell_cache


def runs(chars):
    return re.sub(r'(.)\1{3,}',lambda match:'!'+str(len(match.group(0)))+match.group(1),chars)


@lru_cache(maxsize=24)
def sixel(path,mtime,width,height):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGBA')
        bg=Image.new('RGBA',im.size,(20,24,36,255));bg.alpha_composite(im)
        im=bg.convert('RGB').resize((width,height),Image.Resampling.LANCZOS).quantize(colors=128)
    palette=im.getpalette();pixels=im.load();out=['\033P0;1q',f'"1;1;{width};{height}']
    colors=sorted({pixels[x,y] for y in range(height) for x in range(width)})
    for color in colors:
        rgb=[round(v*100/255) for v in palette[color*3:color*3+3]]
        out.append(f'#{color};2;{rgb[0]};{rgb[1]};{rgb[2]}')
    table=bytes(min(63,index)+63 for index in range(256))
    for top in range(0,height,6):
        masks={}
        for dy in range(min(6,height-top)):
            for x in range(width):
                color=pixels[x,top+dy]
                if color not in masks:masks[color]=bytearray(width)
                masks[color][x]|=1<<dy
        for color,mask in sorted(masks.items()):
            chars=bytes(mask).rstrip(b'\0').translate(table).decode('ascii')
            out.extend([f'#{color}',runs(chars),'$'])
        if top+6<height:out.append('-')
    out.append('\033\\');return ''.join(out)

_lock=threading.RLock()
_rects=[]
_geometry=None
_geometry_time=0

def synchronized(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with _lock:return function(*args,**kwargs)
    return wrapped


def geometry(force=False):
    global _geometry,_geometry_time,_cell_cache,_cell_time
    if not os.environ.get('TMUX'):return (0,0,0,0)
    if force or _geometry is None or time.monotonic()-_geometry_time>.25:
        result=subprocess.run(['tmux','display-message','-p','-t',os.environ['TMUX_PANE'],'#{pane_top} #{pane_left} #{pane_width} #{pane_height} #{window_cell_width} #{window_cell_height}'],capture_output=True,text=True,timeout=1)
        values=result.stdout.split()
        if len(values)==6:
            top,left,width,height,cw,ch=map(int,values)
            _geometry=(top,left,width,height)
            if cw>0 and ch>0:_cell_cache=(cw,ch);_cell_time=time.monotonic()
            _geometry_time=time.monotonic()
    return _geometry or (0,0,0,0)


def emit(payload):
    # Let tmux own SIXEL images. Passthrough images live outside its screen grid
    # and are lost whenever tmux repaints the pane after our write.
    sys.stdout.write(payload);sys.stdout.flush()


@synchronized
def erase_images():
    global _rects
    if not _rects:return
    out=['\0337']
    for row,col,rows,cols,key in _rects:
        for y in range(row,row+rows):out.append(f'\033[{y+1};{col+1}H\033[{cols}X')
    out.append('\0338');emit(''.join(out));_rects=[]


@synchronized
def begin_frame(screen):
    geometry(force=True)
    erase_images()
    screen.redrawwin()


@synchronized
def clear(screen=None,outer=False):
    global _rects
    _rects=[]
    if outer and os.environ.get('TMUX'):
        # Remove graphics emitted by older passthrough versions once at startup.
        payload='\033[2J\033[H'
        sys.stdout.write('\033Ptmux;'+payload.replace('\033','\033\033')+'\033\\');sys.stdout.flush()
    emit('\033[2J\033[H')
    if screen is not None:
        screen.erase();screen.clearok(True);screen.redrawwin();screen.refresh()


@synchronized
def draw(win,path,y,x,cols,rows):
    max_rows,max_cols=win.getmaxyx()
    cols=min(cols,max_cols-x);rows=min(rows,max_rows-y)
    if cols<=0 or rows<=0:return
    cell_w,cell_h=cell_pixels()
    row,col=win.getbegyx();row+=y;col+=x
    top,left,width,height=geometry()
    if width and height:
        cols=min(cols,width-col);rows=min(rows,height-row)
        if cols<=0 or rows<=0:return
    key=(str(path),Path(path).stat().st_mtime_ns,row,col,cols,rows)
    if any(rect[4]==key for rect in _rects):return
    payload='\0337'+f'\033[{row+1};{col+1}H'+sixel(str(path),Path(path).stat().st_mtime_ns,cols*cell_w,max(6,rows*cell_h-rows*cell_h%6))+'\0338'
    emit(payload)
    _rects.append((row,col,rows,cols,key))
