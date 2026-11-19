"""Dark editorial assets using five existing studies; no application UI is painted."""
import json
from pathlib import Path
from PIL import Image,ImageDraw
from render_editorial import artwork,ascii_logo,text,SANS,ROOT
OUT=ROOT/'docs/assets'
SELECTED=(0,2,3,4,7)
SCENES={'collection':('lissajous','nautilus_shell'),'music':('truchet_tiles','dune_contours'),'daily':('iris_filaments','porcelain'),'gallery':('flowers','fern'),'minimal':('phyllotaxis','rose'),'experimental':('light_bloom','rose')}
PALETTES={
 'collection':('#101319','#e4e7ee','#506ccc','#bd8ba9'),
 'music':('#10181c','#e0e8e5','#517b9a','#8db4a8'),
 'daily':('#101725','#e5e9f2','#5277bb','#b58ea6'),
 'gallery':('#181321','#e9e2ed','#8c77b1','#c58ba6'),
 'minimal':('#11151d','#e6e8ee','#536cbd','#b0829a'),
 'experimental':('#152258','#e8ebfa','#6881dd','#ce8caf')}

def wallpaper(name,occupied=()):
 bg,fg,a,b=PALETTES[name];image=Image.new('RGB',(1920,1080),bg)
 first,second=SCENES[name]
 # Art lives on the desktop; protected window regions stay calm and uniform.
 artwork(image,first,(10,30,1900,1020),13,a,8,12)
 artwork(image,second,(1100,0,810,1080),7,b,8,12)
 draw=ImageDraw.Draw(image)
 # Deliberately placed fragments occupy free margins, not the application panels.
 artwork(image,second,(700,0,720,76),7,b,6,8)
 if name in ('music','daily'):
  artwork(image,first,(1200,820,650,210),13,a,6,9)
  artwork(image,second,(1470,820,360,210),7,b,6,9)
 elif name=='gallery':
  artwork(image,'flowers',(130,820,1660,210),8,b,7,9)
 # Final protection also covers the small, layout-specific fragments.
 draw=ImageDraw.Draw(image)
 for x,y,w,h in occupied:draw.rectangle((x-12,y-35,x+w+12,y+h+12),fill=bg)
 # Sparse typographic rails remain outside every terminal.
 text(draw,(42,22),'ttools / '+name.upper(),18,fg)
 text(draw,(1480,22),'ASCII WORKSPACE / 26',16,a)
 draw.line((42,1041,1878,1041),fill=a,width=1)
 text(draw,(42,1052),'MUSIC   /   MESSAGES   /   MOTION',14,fg)
 text(draw,(1560,1052),'200 FX + 19 TOOLS',14,b)
 return image

def section(name,number,label,phrase,accent):
 bg,fg,a,b=PALETTES[name];image=Image.new('RGB',(1600,240),bg)
 first,second=SCENES[name]
 artwork(image,first,(750,-80,820,430),13,a,7,10)
 artwork(image,second,(1150,-70,430,390),9,b,7,10)
 draw=ImageDraw.Draw(image)
 text(draw,(40,30),number,20,accent)
 text(draw,(112,24),label,46,fg,SANS)
 text(draw,(112,99),phrase,24,fg)
 text(draw,(112,184),'TTOOLS / TERMINAL COLLECTION',15,a)
 draw.line((40,224,1560,224),fill=a,width=1)
 image.save(OUT/f'section-{name}.png')

def hero():
 bg,fg,a,b=PALETTES['experimental'];image=Image.new('RGB',(1600,900),bg)
 artwork(image,'light_bloom',(850,115,740,650),16,'#6d8bff',7,11)
 artwork(image,'rose',(1130,70,410,390),6,'#d093b6',7,11)
 ascii_logo(image,(60,115,910,315),fg)
 draw=ImageDraw.Draw(image)
 text(draw,(60,40),'TTOOLS / TERMINAL COLLECTION',20,fg)
 text(draw,(1380,40),'VOL. 03',20,fg)
 text(draw,(72,505),'Всё важное',64,fg,SANS)
 text(draw,(72,587),'в вашем терминале.',64,fg,SANS)
 text(draw,(72,715),'МУЗЫКА / СООБЩЕНИЯ / ДВИЖЕНИЕ',19,'#adbadb')
 draw.line((60,812,1540,812),fill='#657ac0',width=1)
 for x,label in ((60,'tspotify'),(390,'ttelegram'),(760,'TVPN'),(1110,'tthings')):text(draw,(x,837),label,23,fg)
 image.save(OUT/'ascii-hero.png')

def gallery():
 image=Image.new('RGB',(1600,900),'#11151d');draw=ImageDraw.Draw(image)
 text(draw,(42,30),'tthings / формы из символов',26,'#e5e8ef')
 text(draw,(1270,38),'200 FX / 19 TOOLS',17,'#bb8eac')
 for i,name in enumerate(('flowers','fern','porcelain','phyllotaxis','light_bloom','guilloche')):
  x=20+(i%3)*530;y=110+(i//3)*370
  artwork(image,name,(x,y,510,290),13,('#d4a1b9','#8c91be','#bcb3da','#688cde','#9aadd0','#b97f9e')[i],7,11)
  text(draw,(x+24,y+310),name,19,'#c9d0df')
 image.save(OUT/'ascii-gallery.png')

def main():
 hero();gallery()
 for args in (('music','01','tspotify','Музыка, которую видно.','#78b89b'),('daily','02','ttelegram','Разговор остаётся в центре.','#7b9dcc'),('collection','03','TVPN','Сеть на виду.','#b49bcc'),('gallery','04','tthings','200 эффектов. 19 инструментов.','#c68ba9')):section(*args)
 # Keep a useful dark wallpaper asset; capture layouts request their own variants.
 wallpaper('experimental').save(OUT/'ascii-wallpaper.png')
 (OUT/'editorial-selection.json').write_text(json.dumps({'studies':list(SELECTED),'purpose':{'0':'hero / light_bloom + rose','2':'messages / iris_filaments + porcelain','3':'network / lissajous + nautilus_shell','4':'music / truchet_tiles + dune_contours','7':'botanics / flowers + fern'},'wallpapers':{k:{'effects':SCENES[k],'palette':v} for k,v in PALETTES.items()}},ensure_ascii=False,indent=2)+'\n')
 print('Dark hero, four section artworks, gallery and layout-aware wallpaper API ready.',flush=True)
if __name__=='__main__':main()
