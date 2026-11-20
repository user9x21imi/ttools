"""Audit catalog kinds, render every built-in scene and produce review contact sheets."""
import collections,hashlib,json,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'components/tthings/source'))
from tthings import __version__
from tthings.catalog import BUILTINS,ENTRIES,SYSTEM_TOOLS
from tthings.effects import Scene
FONT=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',10)
LABEL=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',12)
PALETTE=['#24242a','#274ccb','#b94d83','#71629a']

def glyph(draw,x,y,char,color):
 if 0x2800<=ord(char)<=0x28ff:
  bits=ord(char)-0x2800
  for bit,dx,dy in ((1,1,0),(2,1,2),(4,1,4),(64,1,6),(8,4,0),(16,4,2),(32,4,4),(128,4,6)):
   if bits&bit:draw.point((x+dx,y+dy),fill=color)
 else:draw.text((x,y-2),char,font=FONT,fill=color)

def main():
 output=ROOT/'docs/assets/catalog';output.mkdir(parents=True,exist_ok=True)
 records=[];tiles=[];errors=[]
 for i,entry in enumerate(BUILTINS):
  start=time.perf_counter();scene=Scene(entry.id,seed=23);frames=[]
  try:
   for elapsed in (1.,8.,16.):frames.append(scene.render(48,16,elapsed))
   ms=(time.perf_counter()-start)/3*1000
   frame=frames[1];fingerprint=hashlib.sha256(('\n'.join(frame.plain() for frame in frames)).encode()).hexdigest()
   ink=sum(ch!=' ' for row in frame.cells for ch,_ in row)
   records.append({'id':entry.id,'title':entry.title,'category':entry.category,'render_ms_48x16':round(ms,2),'ink_cells':ink,'fingerprint':fingerprint})
   tile=Image.new('RGB',(308,174),'#f1efe7');draw=ImageDraw.Draw(tile)
   draw.text((10,7),f'{i+1:03} / {entry.id}',font=LABEL,fill='#24242a')
   color=PALETTE[(i//40)%len(PALETTE)]
   for y,row in enumerate(frame.cells):
    for x,(char,_) in enumerate(row):
     if char!=' ':glyph(draw,10+x*6,32+y*8,char,color)
   draw.text((10,161),f'{ms:.1f} ms',font=FONT,fill='#777579');tiles.append(tile)
  except Exception as error:errors.append({'id':entry.id,'error':str(error)})
 for page in range((len(tiles)+39)//40):
  image=Image.new('RGB',(2464,870),'#dfddd6')
  for index,tile in enumerate(tiles[page*40:(page+1)*40]):image.paste(tile,((index%8)*308,(index//8)*174))
  image.save(output/f'sheet-{page+1:02}.jpg',quality=87)
 grouped=collections.defaultdict(list)
 for record in records:grouped[record['fingerprint']].append(record['id'])
 report={'version':__version__,'counting':{'effects':len(BUILTINS),'tools':len(SYSTEM_TOOLS),'built_in_modes':len(BUILTINS)+len(SYSTEM_TOOLS),'external_links':sum(e.kind=='external' for e in ENTRIES)},'categories':dict(collections.Counter(e.category for e in BUILTINS)),'sampling':{'size':[48,16],'times':[1,8,16],'seed':23},'errors':errors,'identical_samples':[v for v in grouped.values() if len(v)>1],'scenes':records}
 (ROOT/'docs/effects-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'counts':report['counting'],'errors':errors,'identical_samples':report['identical_samples'],'slowest':sorted(records,key=lambda x:x['render_ms_48x16'],reverse=True)[:8]},ensure_ascii=False),flush=True)
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
