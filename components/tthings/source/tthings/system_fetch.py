"""Autonomous system view and a generic 3D renderer for bundled OS logos."""
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from .effects import Frame,FG,DIM

STRUCTURE='Logo:OS:Host:Kernel:Uptime:DE:WM:CPU:GPU:Memory:Disk:Battery'
ANSI=['#10151c','#e47a7a','#9dcc8d','#e8c16d','#82aee8','#caa0de','#79d7cb','#dbe5ee','#536779','#f09292','#c0e3ad','#f8d690','#adcaf2','#e1b6ed','#a3ece2','#ffffff']




def logo_color(code):
    match=re.fullmatch(r'(?:1;)?(3[0-7]|9[0-7])',code)
    if match:
        n=int(match[1]);return ANSI[n-30 if n<40 else n-90+8]
    fields=code.split(';')
    if len(fields)==5 and fields[:2]==['38','2']:
        try:return '#%02x%02x%02x'%tuple(max(0,min(255,int(n))) for n in fields[2:])
        except ValueError:pass
    return '#82aee8'


def parse_logo(result):
    lines=result.get('lines','').splitlines();colors=[logo_color(c) for c in result.get('colors',[])] or ['#82aee8']
    cells=[];color=colors[0]
    for y,line in enumerate(lines):
        x=0;pos=0
        while pos<len(line):
            if line[pos]=='$' and pos+1<len(line) and line[pos+1].isdigit():
                index=int(line[pos+1])-1
                if 0<=index<len(colors):color=colors[index]
                pos+=2;continue
            char=line[pos]
            if char.isprintable() and char!=' ':cells.append((x,y,char,color))
            x+=1;pos+=1
    if not cells:raise ValueError('fastfetch не вернул пиксели логотипа')
    minx=min(c[0] for c in cells);miny=min(c[1] for c in cells)
    cells=[(x-minx,y-miny,ch,color) for x,y,ch,color in cells]
    return cells,max(c[0] for c in cells)+1,max(c[1] for c in cells)+1


def info_rows(modules):
    rows=[];os_name=platform.system()
    def add(label,value):
        if value not in ('',None,[],{}):rows.append((label,str(value)))
    def size(n):
        try:return f'{n/1024**3:.1f} GiB'
        except TypeError:return '—'
    for module in modules:
        name=module.get('type','');value=module.get('result')
        if value is None or name=='Logo':continue
        if name=='OS' and isinstance(value,dict):
            os_name=value.get('prettyName') or value.get('name') or os_name;add('OS',os_name)
        elif name=='Host' and isinstance(value,dict):add('Host',' '.join(str(value.get(k) or '') for k in ('vendor','name')).strip())
        elif name=='Kernel' and isinstance(value,dict):add('Kernel',value.get('release'));add('Arch',value.get('architecture'))
        elif name=='Uptime' and isinstance(value,dict):
            seconds=int(value.get('uptime',0)/1000);add('Uptime',f'{seconds//3600}h {seconds%3600//60}m')
        elif name in ('DE','WM') and isinstance(value,dict):add(name,value.get('prettyName') or value.get('processName'))
        elif name=='CPU' and isinstance(value,dict):
            add('CPU',value.get('cpu'));cores=value.get('cores',{});add('Threads',cores.get('logical') if isinstance(cores,dict) else None)
        elif name=='GPU' and isinstance(value,list):
            for gpu in value:add('GPU',gpu.get('name'))
        elif name=='Memory' and isinstance(value,dict):add('Memory',size(value.get('used'))+' / '+size(value.get('total')))
        elif name=='Disk' and isinstance(value,list):
            for disk in value:
                space=disk.get('bytes',{});add('Disk '+str(disk.get('mountpoint','')),size(space.get('used'))+' / '+size(space.get('total')))
        elif name=='Battery' and isinstance(value,list):
            for bat in value:
                status=bat.get('status','');status=' / '.join(status) if isinstance(status,list) else str(status)
                add('Battery',str(bat.get('capacity','—'))+'% '+status)
    return os_name,rows


class SystemData:
    def __init__(self):
        self.stop=threading.Event();self.lock=threading.Lock();self.data=None;self.error=None
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        from .os_info import gather_system_data
        while not self.stop.is_set():
            try:
                data=gather_system_data()
                with self.lock:self.data=data;self.error=None
            except (OSError,ValueError,KeyError,TypeError) as exc:
                with self.lock:self.error='Сведения о системе: '+str(exc)
            self.stop.wait(15)
    def read(self):
        with self.lock:return self.data,self.error

FastfetchData=SystemData # Backward compatibility for development preview scripts.


def glyph_mask(char):
    """2x4 coverage for ASCII logo ink; punctuation must not become solid bricks."""
    patterns={'.':[(0,3),(1,3)],',':[(1,2),(0,3)],"'":[(0,0),(1,0)],'`':[(0,0),(1,1)],
              '_':[(0,3),(1,3)],'-':[(0,1),(1,1)],':':[(0,1),(0,3)],';':[(1,1),(1,2),(0,3)],
              '/':[(1,0),(1,1),(0,2),(0,3)],'\\':[(0,0),(0,1),(1,2),(1,3)],
              '+':[(0,1),(1,1),(1,0),(1,2)],'|':[(0,y) for y in range(4)]}
    if char in patterns:return patterns[char]
    if char in ('░','▒'):return [(0,0),(1,1),(0,2),(1,3)]
    return [(x,y) for y in range(4) for x in range(2)]


class Logo3D:
    """Ray-cast the library logo as a colored extrusion at 2x4 subcell resolution."""
    def __init__(self,logo):
        cells,width,height=logo
        self.width=width*2;self.height=height*4;self.mask={}
        norm=max(width*.5,height,1)
        self.ex=width/(2*norm);self.ey=height/norm;self.ez=.09
        for x,y,char,color in cells:
            for dx,dy in glyph_mask(char):self.mask[(x*2+dx,y*4+dy)]=color
        self.points=self.mask # Compatibility for diagnostics; these are ink samples.

    def render(self,width,height,t,style='blocks',size=0):
        f=Frame(width,height);W,H=f.w*2,f.h*4
        angle=math.sin(t*.32)*.7;tilt=.05*math.sin(t*.19)
        # A restrained turn keeps the logo recognizable, rather than presenting
        # a mirrored slab for half of every cycle.
        ca,sa=math.cos(angle),math.sin(angle);ct,st=math.cos(tilt),math.sin(tilt)
        def rotate(x,y,z):
            rx=x*ca+z*sa;rz=z*ca-x*sa
            return rx,y*ct-rz*st,y*st+rz*ct
        def inverse(x,y,z):
            ry=y*ct+z*st;rz=-y*st+z*ct
            return x*ca-rz*sa,ry,x*sa+rz*ca
        projections=[]
        for x in (-self.ex,self.ex):
            for y in (-self.ey,self.ey):
                for z in (-self.ez,self.ez):
                    x2,y2,z2=rotate(x,y,z);factor=4/(4-z2);projections.append((x2*factor,y2*factor))
        left=min(x for x,y in projections);right=max(x for x,y in projections)
        top=min(y for x,y in projections);bottom=max(y for x,y in projections)
        scale=max(.1,min(max(1,W-4)/max(.01,right-left),max(1,H-4)/max(.01,bottom-top)))*max(.6,1+size*.08)
        cx=(left+right)/2;cy=(top+bottom)/2;origin=inverse(0,0,4)
        extents=(self.ex,self.ey,self.ez);groups={};dots=((1,8),(2,16),(4,32),(64,128))
        for py in range(H):
            sy=(py+.5-H/2)/scale+cy
            for px in range(W):
                sx=(px+.5-W/2)/scale+cx;direction=inverse(sx,sy,-4)
                enter=-1e30;leave=1e30;normal_axis=2;miss=False
                for axis in range(3):
                    o=origin[axis];d=direction[axis];extent=extents[axis]
                    if abs(d)<1e-9:
                        if abs(o)>extent:miss=True;break
                        continue
                    a=(-extent-o)/d;b=(extent-o)/d
                    lo=min(a,b);hi=max(a,b)
                    if lo>enter:enter=lo;normal_axis=axis
                    leave=min(leave,hi)
                    if leave<enter:miss=True;break
                if miss or leave<0:continue
                distance=max(0,enter)+1e-7
                step=max(1e-6,(leave-distance)/32)
                color=None;normal=[0.,0.,0.]
                for iteration in range(33):
                    x=origin[0]+distance*direction[0];y=origin[1]+distance*direction[1]
                    ix=min(self.width-1,max(0,int((x/self.ex+1)*.5*self.width)))
                    iy=min(self.height-1,max(0,int((y/self.ey+1)*.5*self.height)))
                    color=self.mask.get((ix,iy))
                    if color:
                        axis=normal_axis if iteration==0 else (0 if abs(direction[0])>abs(direction[1]) else 1)
                        normal[axis]=-1 if direction[axis]>0 else 1
                        break
                    distance+=step
                    if distance>leave:break
                if not color:continue
                nx,ny,nz=rotate(*normal)
                brightness=max(.35,min(1,.52+.42*nz-.14*nx-.08*ny))
                rgb=[int(int(color[i:i+2],16)*brightness) for i in (1,3,5)]
                key=(px//2,py//4);bit=dots[py%4][px%2]
                if key not in groups:groups[key]=[0,0,0,0,0]
                g=groups[key];g[0]|=bit;g[1]+=rgb[0];g[2]+=rgb[1];g[3]+=rgb[2];g[4]+=1
        for (x,y),(bits,r,g,b,count) in groups.items():
            if style=='blocks':ink={255:'█',27:'▀',228:'▄',71:'▌',184:'▐'}.get(bits,chr(0x2800+bits))
            elif style=='dots':ink=chr(0x2800+bits)
            elif style=='wire':ink='░' if bits==255 else chr(0x2800+bits)
            else:ink=chr(0x2800+bits)
            f.put(x,y,ink,'#%02x%02x%02x'%(r//count,g//count,b//count))
        return f


def crop_ink(frame):
    points=[(x,y) for y,row in enumerate(frame.cells) for x,(char,color) in enumerate(row) if char!=' ']
    if not points:return Frame(1,1)
    left=min(x for x,y in points);right=max(x for x,y in points);top=min(y for x,y in points);bottom=max(y for x,y in points)
    result=Frame(right-left+1,bottom-top+1)
    result.cells=[row[left:right+1] for row in frame.cells[top:bottom+1]]
    return result


def render_system_info(data,width,height,t,renderer=None,style='blocks',size=0,scroll=0,palette=None):
    import textwrap
    from .effects import PALETTES
    p=palette or PALETTES[0];f=Frame(width,height);renderer=renderer or Logo3D(data['logo'])
    side=width>=80 and height>=20
    logo_w=min(40,max(24,int(width*.36))) if side else max(8,min(40,width-4))
    logo_h=min(20,max(5,height-12)) if side else min(9,max(3,height//3))
    show_logo=side or height>=28
    x=logo_w+6 if side else 2;y=4 if side or not show_logo else 6+logo_h
    if show_logo:
        image=crop_ink(renderer.render(logo_w,logo_h,t,style,size))
        ox=2+max(0,(logo_w-image.w)//2)
        # Top align the actual ink, not an empty full-height logo canvas.
        for py,row in enumerate(image.cells):
            for px,(char,color) in enumerate(row):
                if char!=' ':f.put(ox+px,4+py,char,color)
    f.text(x,y,data['os'],p[0]);f.text(x,y+1,'3D · '+data.get('logo_name','OS'),DIM)
    column=max(1,width-x-2);label_width=min(13,max(5,column//3));value_width=max(1,column-label_width-2)
    lines=[]
    for label,value in data['rows']:
        labels=textwrap.wrap(str(label),label_width,break_long_words=True,break_on_hyphens=False) or ['']
        values=textwrap.wrap(str(value),value_width,break_long_words=True,break_on_hyphens=False) or ['']
        for i in range(max(len(labels),len(values))):lines.append((labels[i] if i<len(labels) else '',values[i] if i<len(values) else ''))
    available=max(1,height-y-9);offset=max(0,min(scroll,max(0,len(lines)-available)))
    for row,(label,value) in enumerate(lines[offset:offset+available],y+3):
        f.text(x,row,label,p[2]);f.text(x+label_width+2,row,value,FG)
    return f
