"""Seeded two-effect editorial studies; static art, never desktop screenshots."""
import json,random,sys
from pathlib import Path
from PIL import Image,ImageDraw
from render_editorial import artwork,ascii_logo,text,SANS,hero,ROOT
OUTPUT=ROOT/'docs/assets/studies'
PALETTES=[('paper/cobalt/rose','#efede6','#242429','#244ed7','#c96a98'),('ink/lilac/ice','#17191f','#ede9df','#b5a0d8','#7a9fb5'),('cream/graphite/acid','#e8e5da','#26282b','#777776','#a34878'),('cobalt/paper/pink','#2444bd','#f4f0df','#d4d7e2','#e19aba'),('rose/ink/plum','#ead5da','#29242d','#464053','#995571'),('chalk/black','#efefea','#232323','#535353','#92928b')]
EFFECTS=['light_bloom','rose','light_ribbons','light_silk','porcelain','phyllotaxis','dune_contours','guilloche','nautilus_shell','iris_filaments','hopf_fibers','light_gyroid','interference','seashell_fan','catenoid_surface','lissajous','fern','flowers','moire_spokes','truchet_tiles','klein','spherical_spiral','butterfly_curve','harmonograph']
def render(spec,elapsed=12,size=(1600,900)):
 name,bg,ink,first,second=PALETTES[spec['palette']];image=Image.new('RGB',(1600,900),bg);d=ImageDraw.Draw(image)
 a,b=spec['effects'];layout=spec['layout'];text(d,(58,36),'TTOOLS / ASCII STUDIES',20,ink);text(d,(1290,36),f"MIX {spec['id']:02}",20,ink)
 if layout==0:
  artwork(image,a,(730,130,840,630),elapsed,first,8,12);artwork(image,b,(1030,130,480,420),elapsed*.8+3,second,8,12)
  ascii_logo(image,(60,130,730,255),ink);text(d,(65,475),'Всё своё.',53,ink,SANS);text(d,(65,542),'В одном терминале.',53,ink,SANS)
 elif layout==1:
  artwork(image,a,(80,135,1040,620),elapsed,first,8,12);artwork(image,b,(600,190,880,560),elapsed*.8+3,second,8,12)
  # Graphic stays separated from the compact label in this composition.
  ascii_logo(image,(1075,70,455,160),ink);text(d,(62,764),'Музыка / сообщения / движение',24,ink)
 else:
  artwork(image,a,(55,200,710,550),elapsed,first,8,12);artwork(image,b,(780,190,755,570),elapsed*.8+3,second,8,12)
  ascii_logo(image,(60,70,640,215),ink);text(d,(900,100),'Один терминал.',35,ink,SANS)
 d=ImageDraw.Draw(image);d.line((58,815,1542,815),fill=ink,width=1)
 text(d,(58,841),f"{a} + {b}",18,ink);text(d,(1180,843),'ttools / tthings',18,ink)
 return image.resize(size) if size!=(1600,900) else image

def main():
 OUTPUT.mkdir(parents=True,exist_ok=True);rng=random.Random(181126);specs=[]
 hero().save(OUTPUT/'mix-00.png')
 for i in range(1,25):
  spec={'id':i,'effects':rng.sample(EFFECTS,2),'palette':(i-1)%6,'layout':((i-1)//6)%3};specs.append(spec);render(spec).save(OUTPUT/f'mix-{i:02}.png')
 for page in range(3):
  board=Image.new('RGB',(1920,1220),'#deddd5');draw=ImageDraw.Draw(board)
  text(draw,(30,18),f'TTOOLS / MIXES {page*8+1:02}—{page*8+8:02}',25)
  for n,spec in enumerate(specs[page*8:page*8+8]):
   x=20+(n%2)*950;y=70+(n//2)*285
   board.paste(render(spec,size=(480,270)).resize((480,270)),(x,y))
   text(draw,(x+505,y+65),f"{spec['id']:02}",38)
   for off,value in enumerate(spec['effects']):text(draw,(x+505,y+125+off*25),value,17)
   text(draw,(x+505,y+205),PALETTES[spec['palette']][0],13)
  board.save(OUTPUT/f'board-{page+1:02}.jpg',quality=92)
 for spec in specs[:6]:
  frames=[render(spec,10+i*.18,(800,450)) for i in range(16)]
  frames[0].save(OUTPUT/f"mix-{spec['id']:02}.gif",save_all=True,append_images=frames[1:],duration=140,loop=0,optimize=True)
 (OUTPUT/'manifest.json').write_text(json.dumps({'seed':181126,'original':'mix-00.png','palettes':PALETTES,'variants':specs},ensure_ascii=False,indent=2)+'\n')
 print('24 variants, original, 3 boards, 6 animations saved',flush=True)
if __name__=='__main__':main()
