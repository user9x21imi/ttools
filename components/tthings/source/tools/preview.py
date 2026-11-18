"""Optional development preview: real terminal cells rendered with pycairo."""
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import cairo
from tthings.metrics import Sampler
from tthings.system_ui import render_monitor,show
from tthings.effects import Frame,PALETTES
from tthings.system_fetch import SystemData,Logo3D,render_system_info

class Capture:
    def __init__(self):self.frames=[]
    def size(self):return 100,32
    def set_title(self,title):pass
    def draw(self,frame):self.frames.append(frame)
    def read(self,timeout):return 'escape'

sampler=Sampler();sampler.sample();time.sleep(.15);sample=sampler.sample();frames=[]
for kind in ['performance','network','disk-io','disk-space','sensors']:
    frame,_=render_monitor(kind,sample,100,32,history=[1,3,8,14,7,8,20,15,31,22])
    frame.text(2,1,'SYSTEMS THINGS / '+kind.upper(),PALETTES[0][0]);frames.append((kind,frame))
for kind in ['calendar','stopwatch','timezones']:
    capture=Capture();show(capture,kind);frames.append((kind,capture.frames[-1]))
fetch=SystemData()
try:
    for _ in range(100):
        data,error=fetch.read()
        if data or error:break
        time.sleep(.05)
    if data:
        frame=render_system_info(data,100,32,.8)
        frames.append(('Autonomous system view',frame))
finally:fetch.stop.set()
output=Path(__file__).resolve().parent.parent/'previews';output.mkdir(exist_ok=True)
cellw,cellh=9,17;columns=3;tilew,tileh=924,596
surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,tilew*columns,tileh*((len(frames)+columns-1)//columns));ctx=cairo.Context(surface)
ctx.set_source_rgb(.035,.05,.07);ctx.paint()
for index,(title,frame) in enumerate(frames):
    ox=(index%columns)*tilew+12;oy=(index//columns)*tileh+12
    ctx.select_font_face('DejaVu Sans Mono');ctx.set_font_size(12);ctx.set_source_rgb(.6,.7,.8);ctx.move_to(ox,oy+12);ctx.show_text(title)
    ctx.set_source_rgb(.06,.08,.11);ctx.rectangle(ox,oy+24,frame.w*cellw,frame.h*cellh);ctx.fill()
    ctx.set_font_size(14)
    for y,row in enumerate(frame.cells):
        for x,(char,color) in enumerate(row):
            if char==' ':continue
            ctx.select_font_face('DejaVu Sans' if 0x2800<=ord(char)<=0x28ff else 'DejaVu Sans Mono')
            ctx.set_source_rgb(*(int(color[i:i+2],16)/255 for i in (1,3,5)));ctx.move_to(ox+x*cellw,oy+24+y*cellh+14);ctx.show_text(char)
surface.write_to_png(str(output/'systems-0.6.0.png'));print(output/'systems-0.6.0.png')
