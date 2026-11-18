"""Reproducible README studio: offline application captures + real effect renderers."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFilter,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from media_terminal import capture,save_gif,terminal_image,glyph,FONT,SMALL
ASSETS=ROOT/'docs/assets'

class Screen:
    def __init__(self,w=120,h=40):self.w,self.h=w,h;self.cells={}
    def erase(self):self.cells={}
    def getmaxyx(self):return self.h,self.w
    def addnstr(self,y,x,text,n,style):
        pair=style&255
        palette={0:'#dce7ee',1:'#6bd6dd',2:'#58d6a1',3:'#ef6677',4:'#e8bd78',5:'#dce7ee',6:'#536b7c'}
        for i,ch in enumerate(text[:n]):self.cells[(y,x+i)]=(ch,palette.get(pair,'#dce7ee'),'#0c1219',bool(style&(1<<20)))
    def refresh(self):pass

def vpn_frames():
    source=ROOT/'components/tvpn/source';sys.path.insert(0,str(source))
    spec=importlib.util.spec_from_file_location('tvpn_media',source/'riseup-panel.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.Model();model.art='unicode';model.detail='ДЕМО · карта вращается без подключения VPN';model.ip='DEMO / NO TUNNEL';model.region='Нидерланды';model.gateway='—';model.interface='—'
    model.globe=SimpleNamespace(box=None,zoom=1.,latitude=25.,longitude=0.,select=lambda *args:None,tick=lambda:None)
    frames=[]
    for i in range(32):
        model.globe.longitude=-55+i*4
        model.state='off' if i>=26 else 'connecting'
        screen=Screen()
        with patch('curses.color_pair',side_effect=lambda n:n):module.draw(screen,model,False,model.state=='off')
        frames.append(terminal_image(screen.cells,'TVPN / OFFLINE GLOBE PREVIEW','#af87ff',120,40,'OFFLINE RENDERER · NO VPN CONNECTION · NO REAL IP'))
    return frames

def effect_cards():
    sys.path.insert(0,str(ROOT/'components/tthings/source'))
    from tthings.renderer import create_renderer,available_effects
    wanted=['light_ribbons','aurora','galaxy','matrix','blackhole','sakura','ocean','globe','fireworks']
    catalog={x['id']:x for x in available_effects()}
    ids=[x for x in wanted if x in catalog]
    renderers=[create_renderer(x,53,15,seed=17+i,brightness=.95) for i,x in enumerate(ids)]
    def card(index,t):
        frame=renderers[index].render(t)
        image=Image.new('RGB',(590,332),'#0c1219');draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((1,1,588,330),radius=16,outline='#344354',width=2)
        draw.text((23,18),catalog[ids[index]]['title'],font=FONT,fill='#f18aca')
        for y,row in enumerate(frame.cells):
            for x,(ch,fg) in enumerate(row):
                if ch!=' ':glyph(draw,(25+x*10,58+y*16),ch,fg)
        draw.text((24,300),ids[index],font=SMALL,fill='#6c8496')
        return image
    frames=[]
    for i in range(30):
        image=Image.new('RGB',(1200,740),'#080e14');draw=ImageDraw.Draw(image)
        draw.text((30,16),'tthings / BEAUTIFUL THINGS',font=FONT,fill='#ff63c5')
        for j in range(4):image.paste(card(j,12+i*.18),(10+(j%2)*600,52+(j//2)*340))
        frames.append(image)
    wall=Image.new('RGB',(1830,1110),'#080e14');draw=ImageDraw.Draw(wall)
    header=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',37)
    draw.text((30,21),'130 ways to make a terminal feel alive.',font=header,fill='#f2eaf3')
    for j in range(min(9,len(ids))):wall.paste(card(j,15),(20+(j%3)*600,88+(j//3)*340))
    return frames,wall

def collage(images):
    image=Image.new('RGB',(1920,1440));pixels=image.load()
    for y in range(image.height):
        for x in range(image.width):
            glow=max(0,1-math.hypot((x-1500)/1700,(y-180)/1400))
            pixels[x,y]=(8+int(glow*7),14+int(glow*10),22+int(glow*15))
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',108)
    label=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',27)
    small=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',20)
    draw.line((78,74,137,109,78,144),fill='#1dd787',width=10)
    little=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',65)
    draw.text((165,105),'t',font=little,fill='#eff6fa')
    draw.text((195,38),'Tools',font=font,fill='#eff6fa')
    draw.line((202,160,555,160),fill='#eff6fa',width=7)
    draw.text((78,201),'Music. Messages. Privacy. Motion.',font=label,fill='#a7bfcc')
    draw.text((1290,96),'ONE TERMINAL.',font=label,fill='#8aaabf')
    draw.text((1290,134),'ALL YOUR TOOLS.',font=label,fill='#e5f2f6')
    labels=[('01 / SPOTIFY','#1dd787'),('02 / TELEGRAM','#53aeef'),('03 / TVPN','#af87ff'),('04 / TTHINGS','#ff63c5')]
    positions=[(55,330),(1005,330),(55,900),(1005,900)]
    for index,(snapshot,(x,y),(title,accent)) in enumerate(zip(images,positions,labels)):
        draw.text((x+12,y-53),title,font=label,fill=accent)
        card=snapshot.copy();card.thumbnail((860,485),Image.Resampling.LANCZOS)
        layer=Image.new('RGBA',(920,540));shadow=Image.new('RGBA',layer.size);sd=ImageDraw.Draw(shadow)
        sd.rounded_rectangle((22,20,card.width+30,card.height+30),radius=20,fill=(0,0,0,150))
        shadow=shadow.filter(ImageFilter.GaussianBlur(12));layer.alpha_composite(shadow)
        layer.paste(card,(15,8));layer=layer.rotate(1.5 if index%2==0 else -1.5,resample=Image.Resampling.BICUBIC,expand=False)
        image.paste(layer,(x,y),layer)
    draw.text((78,1400),'OFFLINE DEMOS / FICTIONAL MESSAGES / REAL RENDERERS / NO ACCOUNT DATA',font=small,fill='#6c899c')
    return image

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suite-prefix',required=True,type=Path);parser.add_argument('--only-telegram',action='store_true');args=parser.parse_args()
    state=json.loads((args.suite_prefix/'state.json').read_text())
    release=Path(state['release'])
    apps=json.loads((release/'apps.local.json').read_text())['apps']
    spotify=next(a for a in apps if a['id']=='tspotify')
    telegram=release/'apps/ttelegram/current'
    ASSETS.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ttools-media-') as folder:
        folder=Path(folder)
        env={name:str(folder/name) for name in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','TSPOTIFY_CONFIG_DIR','TSPOTIFY_CACHE_DIR','TSPOTIFY_DATA_DIR')}
        for path in env.values():Path(path).mkdir()
        if not args.only_telegram:
            spotify_frames=capture([*spotify['command'],'--demo','--no-splash'],dict(env,**spotify.get('env',{})),'tspotify / OFFLINE DEMO','#1dd787',actions=[(1.5,b' '),(2.8,b'2'),(4.1,b'1'),(5.1,b' ')],seconds=6.8)
            save_gif(spotify_frames,ASSETS/'spotify.gif');spotify_frames[len(spotify_frames)//2].save(ASSETS/'spotify.png');print('Spotify offline capture: done',flush=True)
        # Synthetic artwork goes through the real Telegram media renderer.
        from PIL import ImageDraw
        poster=Image.new('RGB',(520,300),'#111a2c');pd=ImageDraw.Draw(poster)
        for i in range(26):pd.ellipse((60+i*8,15+i*3,440-i*4,285-i*2),outline=(50+i*6,190-i*3,230),width=4)
        poster.save(folder/'poster.png')
        telegram_env=dict(env,TTOOLS_MEDIA_DIR=str(folder),TTELEGRAM_TEST_RUNTIME=str(ROOT/'components/ttelegram/source'))
        telegram_frames=capture([telegram/'venv/bin/python',ROOT/'tools/media_telegram_fixture.py'],telegram_env,'ttelegram / FICTIONAL CHAT PREVIEW','#53aeef',actions=[(1.3,b'\n'),(2.1,'Всё в одном месте.'.encode()),(3.2,b'\x0f'),(4.4,b'\t'),(5.6,b'\t'),(6.8,b'\x1b'),(7.6,b'\x0c'),(8.4,b'\n')],seconds=9.4,caption='FAKE BACKEND · FICTIONAL MESSAGES · NO TELEGRAM LOGIN')
        save_gif(telegram_frames,ASSETS/'telegram.gif');telegram_frames[min(7,len(telegram_frames)-1)].save(ASSETS/'telegram.png');print('Telegram fake-runtime capture: done',flush=True)
    if args.only_telegram:
        collage([Image.open(ASSETS/name).convert('RGB') for name in ('spotify.png','telegram.png','vpn.png','tthings.png')]).save(ASSETS/'showcase.png')
        return
    vpn=vpn_frames();save_gif(vpn,ASSETS/'vpn.gif');vpn[12].save(ASSETS/'vpn.png');print('VPN offline globe: done',flush=True)
    things,wall=effect_cards();save_gif(things,ASSETS/'tthings.gif');things[15].save(ASSETS/'tthings.png');wall.save(ASSETS/'effects-wall.png');print('tthings real renderer gallery: done',flush=True)
    collage([spotify_frames[len(spotify_frames)//2],telegram_frames[min(7,len(telegram_frames)-1)],vpn[12],things[15]]).save(ASSETS/'showcase.png')
    print('Showcase collage: done',flush=True)

if __name__=='__main__':main()
