"""Small VT capture adapter used only to render account-free documentation demos."""
import codecs
import colorsys
import fcntl
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import termios
import time
import unicodedata
from PIL import Image,ImageDraw,ImageFont

FONT=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',16)
SMALL=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',12)
BOLD=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf',16)
ANSI=['#17232e','#ef6677','#58d6a1','#e8bd78','#66aceb','#bd8df4','#6bd6dd','#dce7ee','#536b7c','#ff7b8b','#7ce8b7','#f5d296','#8cc5f6','#d7acf8','#94e4e8','#f4f7fa']
def color(number):
    if number<16:return ANSI[number]
    if number>=232:
        n=8+(number-232)*10;return '#%02x%02x%02x'%(n,n,n)
    n=number-16;steps=[0,95,135,175,215,255]
    return '#%02x%02x%02x'%(steps[n//36],steps[(n//6)%6],steps[n%6])

class VT:
    def __init__(self,width=112,height=34):
        self.width,self.height=width,height;self.x=self.y=0;self.fg='#dce7ee';self.bg='#0c1219';self.bold=False;self.inverse=False;self.state='text';self.sequence='';self.saved=(0,0);self.charset=False;self.cells={};self.decoder=codecs.getincrementaldecoder('utf-8')('replace')
    def blank(self):return (' ',self.fg,self.bg,self.bold)
    def feed(self,data):
        for ch in self.decoder.decode(data):
            if self.state=='dcs':
                if ch=='\x1b':self.state='dcs-end'
                continue
            if self.state=='dcs-end':
                self.state='text' if ch=='\\' else 'dcs';continue
            if self.state=='osc':
                if ch=='\a':self.state='text'
                elif ch=='\x1b':self.state='osc-end'
                continue
            if self.state=='osc-end':
                self.state='text' if ch=='\\' else 'osc';continue
            if self.state=='charset':self.charset=ch=='0';self.state='text';continue
            if self.state=='escape':
                if ch=='[':self.state='csi';self.sequence=''
                elif ch==']':self.state='osc'
                elif ch=='P':self.state='dcs'
                elif ch in ('(',')'):self.state='charset'
                elif ch=='7':self.saved=(self.x,self.y);self.state='text'
                elif ch=='8':self.x,self.y=self.saved;self.state='text'
                else:self.state='text'
                continue
            if self.state=='csi':
                if '@'<=ch<='~':self.csi(ch,self.sequence);self.state='text'
                else:self.sequence+=ch
                continue
            if ch=='\x1b':self.state='escape'
            elif ch=='\r':self.x=0
            elif ch=='\n':self.y=min(self.height-1,self.y+1)
            elif ch=='\b':self.x=max(0,self.x-1)
            elif ch=='\t':self.x=min(self.width-1,(self.x//8+1)*8)
            elif ch.isprintable():
                if self.charset:ch={'q':'─','x':'│','l':'┌','k':'┐','m':'└','j':'┘','t':'├','u':'┤','v':'┴','w':'┬','n':'┼'}.get(ch,ch)
                fg,bg=(self.bg,self.fg) if self.inverse else (self.fg,self.bg)
                if 0<=self.x<self.width and 0<=self.y<self.height:self.cells[(self.y,self.x)]=(ch,fg,bg,self.bold)
                self.x+=2 if unicodedata.east_asian_width(ch) in ('W','F') else 0 if unicodedata.combining(ch) else 1
                if self.x>=self.width:self.x=0;self.y=min(self.height-1,self.y+1)
    def csi(self,final,text):
        private=text.startswith('?');raw=text.lstrip('?=>')
        try:args=[int(v or 0) for v in raw.split(';')]
        except ValueError:return
        first=args[0] or 1
        if final in ('H','f'):self.y=max(0,min(self.height-1,first-1));self.x=max(0,min(self.width-1,(args[1] or 1)-1 if len(args)>1 else 0))
        elif final=='A':self.y=max(0,self.y-first)
        elif final=='B':self.y=min(self.height-1,self.y+first)
        elif final=='C':self.x=min(self.width-1,self.x+first)
        elif final=='D':self.x=max(0,self.x-first)
        elif final=='G':self.x=max(0,min(self.width-1,first-1))
        elif final=='d':self.y=max(0,min(self.height-1,first-1))
        elif final=='E':self.x=0;self.y=min(self.height-1,self.y+first)
        elif final=='F':self.x=0;self.y=max(0,self.y-first)
        elif final=='s':self.saved=(self.x,self.y)
        elif final=='u':self.x,self.y=self.saved
        elif final=='J':
            mode=args[0]
            for y in range(self.height):
                for x in range(self.width):
                    if mode in (2,3) or mode==0 and (y,x)>=(self.y,self.x) or mode==1 and (y,x)<=(self.y,self.x):self.cells[(y,x)]=self.blank()
        elif final=='K':
            mode=args[0]
            for x in range(self.width):
                if mode==2 or mode==0 and x>=self.x or mode==1 and x<=self.x:self.cells[(self.y,x)]=self.blank()
        elif final=='X':
            for x in range(self.x,min(self.width,self.x+first)):self.cells[(self.y,x)]=self.blank()
        elif final=='m':
            i=0
            while i<len(args):
                n=args[i]
                if n==0:self.fg,self.bg,self.bold,self.inverse='#dce7ee','#0c1219',False,False
                elif n==1:self.bold=True
                elif n in (2,22):self.bold=False
                elif n==7:self.inverse=True
                elif n==27:self.inverse=False
                elif n==39:self.fg='#dce7ee'
                elif n==49:self.bg='#0c1219'
                elif 30<=n<=37:self.fg=color(n-30)
                elif 40<=n<=47:self.bg=color(n-40)
                elif 90<=n<=97:self.fg=color(n-90+8)
                elif 100<=n<=107:self.bg=color(n-100+8)
                elif n in (38,48) and i+2<len(args):
                    if args[i+1]==5:chosen=color(args[i+2]);i+=2
                    elif args[i+1]==2 and i+4<len(args):chosen='#%02x%02x%02x'%tuple(args[i+2:i+5]);i+=4
                    else:i+=1;continue
                    if n==38:self.fg=chosen
                    else:self.bg=chosen
                i+=1

def glyph(draw,xy,ch,fg,font=FONT):
    x,y=xy
    if 0x2800<=ord(ch)<=0x28ff:
        bits=ord(ch)-0x2800
        for bit,dx,dy in [(1,2,2),(2,2,6),(4,2,10),(64,2,14),(8,7,2),(16,7,6),(32,7,10),(128,7,14)]:
            if bits&bit:draw.ellipse((x+dx,y+dy,x+dx+1,y+dy+1),fill=fg)
    else:draw.text((x,y-1),ch,font=font,fill=fg)

def terminal_image(cells,title,accent,width=112,height=34,caption='OFFLINE DEMO · NO ACCOUNT DATA'):
    canvas=Image.new('RGB',(width*10+80,height*18+104),'#080e14');draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((12,12,canvas.width-12,canvas.height-12),radius=18,fill='#0c1219',outline='#263d4c',width=2)
    for x,c in [(36,'#ff615a'),(57,'#ffbd2e'),(78,'#28c840')]:draw.ellipse((x,31,x+10,41),fill=c)
    draw.text((118,27),title,font=SMALL,fill=accent)
    for (y,x),(ch,fg,bg,bold) in cells.items():
        px=40+x*10;py=62+y*18
        if bg and bg not in ('#0c1219','#000000'):draw.rectangle((px,py,px+10,py+18),fill=bg)
        if ch!=' ':glyph(draw,(px,py),ch,fg,BOLD if bold else FONT)
    draw.text((40,canvas.height-34),caption,font=SMALL,fill='#627e90')
    return canvas

def capture(argv,env,title,accent,actions=(),seconds=7,width=112,height=34,caption='OFFLINE DEMO · NO ACCOUNT DATA'):
    master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',height,width,0,0))
    child=subprocess.Popen(list(map(str,argv)),stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,**env,TERM='xterm-256color'),start_new_session=True)
    os.close(slave);vt=VT(width,height);started=time.monotonic();next_frame=1.;index=0;frames=[];raw=bytearray()
    try:
        while time.monotonic()-started<seconds and child.poll() is None:
            elapsed=time.monotonic()-started
            while index<len(actions) and elapsed>=actions[index][0]:os.write(master,actions[index][1]);index+=1
            if select.select([master],[],[],.03)[0]:
                try:data=os.read(master,262144)
                except OSError:break
                raw.extend(data);vt.feed(data)
            if elapsed>=next_frame:
                if sum(ch!=' ' for ch,fg,bg,bold in vt.cells.values())>80:
                    frames.append(terminal_image(dict(vt.cells),title,accent,width,height,caption))
                next_frame+=.20
        if child.poll() is None:
            os.write(master,b'\x11')
            try:child.wait(timeout=4)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=4)
        if b'Traceback' in raw:raise RuntimeError(raw[-3000:].decode(errors='replace'))
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)
        os.close(master)
    if not frames:raise RuntimeError('No terminal frames captured: '+raw[-1000:].decode(errors='replace'))
    return frames

def save_gif(frames,path,width=1040,duration=200):
    size=(width,round(frames[0].height*width/frames[0].width))
    converted=[frame.resize(size,Image.Resampling.LANCZOS) for frame in frames]
    converted[0].save(path,save_all=True,append_images=converted[1:],duration=duration,loop=0,optimize=True)
