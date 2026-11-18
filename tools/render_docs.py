"""Render actual UI.draw cells for README; no account data and no desktop capture."""
from pathlib import Path
import sys
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ttools.__main__ import UI
from ttools.visuals.effects import Scene

FONT=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',16)
SMALL=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSansMono.ttf',12)
COLORS={1:('#e8f0f4',None),2:('#879aaa',None),3:('#1dd787',None),4:('#53aeef',None),5:('#e8f0f4','#18232e'),6:('#1dd787','#18232e'),7:('#1d303f',None),8:('#283c4b',None)}
for i,(fg,bg) in enumerate([('#1dd787','#173d29'),('#ff8700','#492f14'),('#ff343b','#491b24'),('#53aeef','#142d4b'),('#af87ff','#332044'),('#ff00af','#42132f')]):
    COLORS[9+i*2]=(fg,bg);COLORS[10+i*2]=('#e8f0f4',bg)

class Screen:
    def getmaxyx(self):return 34,112
    def erase(self):self.cells={}
    def addnstr(self,y,x,text,n,style):
        for offset,ch in enumerate(text[:n]):self.cells[(y,x+offset)]=(ch,style&255)
    def refresh(self):pass

def render(t,selection):
    ui=UI.__new__(UI)
    ui.s=Screen();ui.apps=[{'id':name,'name':name,'command':[sys.executable],'version':version} for name,version in [('tspotify','0.1.0'),('ttelegram','2026.11.18.4'),('tvpn','1.3.1'),('tthings','0.7.0')]]
    ui.selected=selection;ui.query='';ui.searching=False;ui.status='Готово к запуску';ui.updates={a['id']:'Обновляет ttools · '+a['version'] for a in ui.apps};ui.jobs={};ui.last_check=0;ui.started=-5;ui.splash=False;ui.effect='particles';ui.scene=Scene('particles',seed=11);ui.effect_start=0;ui.next_effect=120
    with patch('curses.color_pair',side_effect=lambda n:n),patch('ttools.__main__.time.monotonic',return_value=t),patch('ttools.__main__.time.strftime',return_value='12:00'):
        ui.draw()
    image=Image.new('RGB',(1200,740),'#080e14');draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((20,20,1180,720),radius=20,fill='#0c1219',outline='#203141',width=2)
    for x,color in [(44,'#ff615a'),(66,'#ffbd2e'),(88,'#28c840')]:draw.ellipse((x,39,x+10,49),fill=color)
    draw.text((510,35),'ttools / workspace',font=SMALL,fill='#879aaa')
    for (y,x),(ch,pair) in ui.s.cells.items():
        fg,bg=COLORS.get(pair,COLORS[1]);px=40+x*10;py=74+y*18
        if bg:draw.rectangle((px,py,px+10,py+18),fill=bg)
        if 0x2800 <= ord(ch) <= 0x28ff:
            bits=ord(ch)-0x2800
            for bit,dx,dy in [(1,2,2),(2,2,6),(4,2,10),(64,2,14),(8,7,2),(16,7,6),(32,7,10),(128,7,14)]:
                if bits&bit:draw.ellipse((px+dx,py+dy,px+dx+1,py+dy+1),fill=fg)
        elif ch!=' ':draw.text((px,py-1),ch,font=FONT,fill=fg)
    return image

if __name__=='__main__':
    assets=ROOT/'docs/assets';assets.mkdir(parents=True,exist_ok=True)
    render(2,0).save(assets/'interface.png')
    frames=[render(i*.2,(i//6)%4).resize((960,592)) for i in range(24)]
    frames[0].save(assets/'demo.gif',save_all=True,append_images=frames[1:],duration=180,loop=0,optimize=True)
    print('Rendered actual UI cells: interface.png, demo.gif')
