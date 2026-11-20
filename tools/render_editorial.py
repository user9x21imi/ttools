"""Original character-based artwork for the ASCII editorial identity."""
from pathlib import Path
import sys
import math
from functools import lru_cache
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'components/tthings/source'))
from tthings.renderer import create_renderer
PAPER='#efede6';INK='#242429';BLUE='#244ed7';PINK='#c96a98'
MONO='/usr/share/fonts/TTF/DejaVuSansMono.ttf'
BOLD='/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'
SANS='/usr/share/fonts/TTF/DejaVuSans.ttf'

@lru_cache(maxsize=32)
def font(path,size):return ImageFont.truetype(path,size)

def text(draw,xy,value,size=24,color=INK,font=MONO):
 draw.text(xy,value,font=globals()["font"](font,size),fill=color)

def glyph(draw,x,y,char,color,cw=8,ch=12):
 if 0x2800<=ord(char)<=0x28ff:
  bits=ord(char)-0x2800
  for bit,dx,dy in ((1,.25,.12),(2,.25,.35),(4,.25,.58),(64,.25,.81),(8,.7,.12),(16,.7,.35),(32,.7,.58),(128,.7,.81)):
   if bits&bit:
    cx=x+dx*cw;cy=y+dy*ch;r=max(.55,cw*.105)
    draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=color)
 else:draw.text((x,y-2),char,font=font(MONO,max(8,ch-1)),fill=color)

def artwork(image,effect,bounds,elapsed=12.,color=BLUE,cw=8,ch=12):
 x,y,w,h=bounds;cols=max(1,int(w/cw));rows=max(1,int(h/ch))
 frame=create_renderer(effect,cols,rows,seed=31,brightness=1).render(elapsed)
 draw=ImageDraw.Draw(image)
 for row,line in enumerate(frame.cells):
  for col,(char,_) in enumerate(line):
   if char!=' ':glyph(draw,x+col*cw,y+row*ch,char,color,cw,ch)

def ascii_logo(image,bounds,color=INK):
 x,y,w,h=bounds
 mask=Image.new('L',image.size);draw=ImageDraw.Draw(mask)
 size=int(h*.88)
 big=ImageFont.truetype(BOLD,size)
 draw.text((x+w*.07,y-h*.05),'Tools',font=big,fill=255,stroke_width=1)
 draw.text((x,y+h*.40),'t',font=ImageFont.truetype(SANS,int(h*.38)),fill=255)
 draw.line((x+w*.08,y+h*.86,x+w*.94,y+h*.86),fill=255,width=max(3,int(h*.018)))
 paint=ImageDraw.Draw(image);pixels=mask.load();ramp=':+x#%'
 cw,ch=7,10
 for yy in range(max(0,y),min(image.height,y+h),ch):
  for xx in range(max(0,x),min(image.width,x+w),cw):
   samples=[pixels[min(image.width-1,xx+dx),min(image.height-1,yy+dy)] for dx,dy in ((1,1),(3,4),(5,7))]
   if max(samples)>100:
    char=ramp[(xx//cw+yy//ch*3)%len(ramp)]
    glyph(paint,xx,yy,char,color,cw,ch)

def hero():
 image=Image.new('RGB',(1600,900),PAPER);draw=ImageDraw.Draw(image)
 text(draw,(64,43),'TTOOLS / TERMINAL COLLECTION',21)
 text(draw,(1272,43),'VOL. 02',21)
 artwork(image,'light_bloom',(840,115,745,700),16,BLUE,7,11)
 artwork(image,'rose',(1120,90,360,300),6,PINK,7,11)
 ascii_logo(image,(64,120,990,340))
 draw=ImageDraw.Draw(image)
 text(draw,(73,514),'Всё своё.',64,font=SANS)
 text(draw,(73,596),'В одном терминале.',64,font=SANS)
 text(draw,(73,720),'МУЗЫКА / СООБЩЕНИЯ / ДВИЖЕНИЕ',20)
 draw.line((64,816,1536,816),fill=INK,width=1)
 for x,label in ((64,'tspotify'),(380,'ttelegram'),(720,'TVPN'),(1010,'tthings')):text(draw,(x,839),label,23)
 text(draw,(1390,844),'[ enter ]',17,BLUE)
 return image

def wallpaper():
 image=Image.new('RGB',(1920,1080),'#deded4');draw=ImageDraw.Draw(image)
 artwork(image,'phyllotaxis',(1150,65,770,910),13,BLUE,7,11)
 artwork(image,'rose',(1450,160,450,360),5,PINK,7,11)
 ascii_logo(image,(72,60,700,245))
 text(draw,(82,337),'Привычные вещи.',35,font=SANS)
 text(draw,(82,384),'Другой способ открыть.',35,font=SANS)
 draw.line((72,972,1848,972),fill='#aaa99f',width=1)
 text(draw,(72,1005),'TTOOLS / ASCII WORKSPACE',20)
 text(draw,(1510,1005),'200 FX + 19 TOOLS',20,BLUE)
 return image

def gallery(elapsed):
 image=Image.new('RGB',(1600,900),PAPER);draw=ImageDraw.Draw(image)
 text(draw,(54,32),'tthings / формы, собранные из символов',25)
 text(draw,(1270,40),'200 FX / 19 TOOLS',17,BLUE)
 names=['flowers','phyllotaxis','porcelain','guilloche','light_bloom','dune_contours']
 for i,name in enumerate(names):
  x=25+(i%3)*525;y=110+(i//3)*365
  artwork(image,name,(x,y,510,295),elapsed,[INK,BLUE,PINK,BLUE,INK,BLUE][i],7,11)
  text(draw,(x+25,y+311),name,18,[INK,BLUE,PINK,BLUE,INK,BLUE][i])
 return image

def main():
 output=ROOT/'docs/assets';output.mkdir(parents=True,exist_ok=True)
 hero().save(output/'ascii-hero.png')
 wallpaper().save(output/'ascii-wallpaper.png')
 gallery(12).save(output/'ascii-gallery.png')
 frames=[gallery(10+i*.25).resize((960,540)) for i in range(28)]
 frames[0].save(output/'ascii-gallery.gif',save_all=True,append_images=frames[1:],duration=150,loop=0,optimize=True)
 print('Original ASCII hero, workspace wallpaper and gallery generated.')
if __name__=='__main__':main()
