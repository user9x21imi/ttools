"""Native 16:9 demo captures. Xvfb only: never open a window on the host desktop."""
import os,subprocess,time,tempfile,json,shutil,sys
from pathlib import Path
from PIL import Image
from editorial_assets import wallpaper as make_wallpaper
from Xlib import display,X
import argparse
parser=argparse.ArgumentParser(description='Capture native Konsole windows in an invisible, isolated Xvfb desktop')
parser.add_argument('--suite-prefix',type=Path,required=True)
parser.add_argument('--startup-preview',action='store_true')
parser.add_argument('--launcher-preview',action='store_true')
parser.add_argument('--xvfb',default=shutil.which('Xvfb'))
args=parser.parse_args()
if not args.xvfb:parser.error('Xvfb is required; no visible Xwayland fallback is used')
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'docs/assets'
if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):parser.error('Run with dbus-run-session -- python tools/capture_workspaces.py ...')
folder=Path(tempfile.mkdtemp(prefix='ttools-desktop-'))
env=dict(os.environ,DISPLAY=':77',QT_QPA_PLATFORM='xcb',LIBGL_ALWAYS_SOFTWARE='1',TERM='xterm-256color',COLORTERM='truecolor')
for name in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','TSPOTIFY_CONFIG_DIR','TSPOTIFY_CACHE_DIR','TSPOTIFY_DATA_DIR'):
 env[name]=str(folder/name);Path(env[name]).mkdir()
# Standard system palette only: no personal desktop configuration is copied.
standard_dark=Path('/usr/share/color-schemes/BreezeDark.colors')
if standard_dark.is_file():
 (Path(env['XDG_CONFIG_HOME'])/'kdeglobals').write_text(standard_dark.read_text()+'\n[General]\nColorScheme=BreezeDark\n')
profiles=Path(env['XDG_DATA_HOME'])/'konsole';profiles.mkdir()
for name in ('ttools.profile','ttools.colorscheme'):shutil.copy2(ROOT/'konsole'/name,profiles/name)
# One typeface and quiet palette across native terminal windows.
p=profiles/'ttools.profile';p.write_text(p.read_text().replace('Mono,12','Mono,11'))
p=profiles/'ttools.colorscheme';p.write_text(p.read_text().replace('Opacity=0.78','Opacity=0.98'))
children=[]
def start(argv,extra=None):
 log=(folder/f'process-{len(children)}.log').open('w');p=subprocess.Popen([str(x) for x in argv],env=dict(env,**(extra or {})),cwd=ROOT,stdout=log,stderr=log);children.append(p);return p
try:
 server=start([args.xvfb,':77','-ac','-nolisten','tcp','-screen','0','1920x1080x24']);time.sleep(2)
 wm=start(['kwin_x11','--replace','--no-kactivities']);time.sleep(3)
 connection=display.Display(':77');root=connection.screen().root
 wallpaper=make_wallpaper('minimal',[(55,65,1010,650),(1090,100,780,560),(890,690,720,310)])
 pixmap=root.create_pixmap(1920,1080,24);gc=pixmap.create_gc()
 for yy in range(0,1080,20):
  strip=wallpaper.crop((0,yy,1920,min(1080,yy+20)))
  pixmap.put_image(gc,0,yy,1920,strip.height,X.ZPixmap,24,0,strip.tobytes('raw','BGRX'))
 from Xlib import Xatom
 for atom in ('_XROOTPMAP_ID','ESETROOT_PMAP_ID'):root.change_property(connection.intern_atom(atom),Xatom.PIXMAP,32,[pixmap.id])
 root.change_attributes(background_pixmap=pixmap);root.clear_area();connection.sync()
 wallpaper.save(folder/'wallpaper.png')
 wall_code=folder/'wall.py'
 wall_code.write_text("import tkinter as t\nfrom pathlib import Path\nr=t.Tk();r.geometry('1920x1080+0+0');r.attributes('-type','desktop')\np=Path("+repr(str(folder/'wallpaper.png'))+")\nim=None;stamp=None\nlabel=t.Label(r,borderwidth=0);label.pack()\ndef reload():\n global im,stamp\n current=p.stat().st_mtime_ns\n if current!=stamp:\n  im=t.PhotoImage(file=str(p));label.configure(image=im);stamp=current\n r.after(200,reload)\nreload();r.lower();r.mainloop()\n")
 wall=start([sys.executable,wall_code]);time.sleep(1)
 def backdrop(name,rectangles):
  image=make_wallpaper(name,rectangles)
  image.save(folder/'wallpaper-next.png')
  os.replace(folder/'wallpaper-next.png',folder/'wallpaper.png')
  time.sleep(.35)
 catalog=json.loads(((args.suite_prefix/'state.json')).read_text());release=Path(catalog['release']);apps=json.loads((release/'apps.local.json').read_text())['apps']
 # Installed commands are reused, with a fictional catalog and isolated settings.
 for a in apps:
  if a['id']=='tspotify':
   a['command']=[str(release/'apps/tspotify/current/tspotify/tspotify'),'--demo','--no-splash']
   a['env']=dict(a.get('env',{}),TSPOTIFY_INSTALL_PREFIX=str(folder/'launcher-spotify'),TSPOTIFY_UPDATE_OWNER='ttools')
   (folder/'launcher-spotify').mkdir()
  if a['id']=='tthings':a['version']='0.7.2'
 local=folder/'apps.local.json';local.write_text(json.dumps({'apps':[dict(a,update_manifest_url=None,update_owner='ttools') for a in apps]}))
 env['TTOOLS_CONFIG_DIR']=str(folder/'launcher')
 # Core resolves its own XDG config; seed only the isolated source list.
 env['TTOOLS_CATALOG']=str(local)
 def terminal(title,command,x,y,w,h,extra=None,font=11):
  p=start(['konsole','--separate','--profile','ttools','--hide-menubar','--hide-tabbar','--hide-toolbars','-p','LocalTabTitleFormat='+title,'-p',f'Font=DejaVu Sans Mono,{font},-1,5,50,0,0,0,0,0','-e',*command],extra)
  for _ in range(40):
   out=subprocess.run(['xdotool','search','--all','--onlyvisible','--pid',str(p.pid),'--class','konsole'],env=env,capture_output=True,text=True).stdout.split()
   if out:break
   time.sleep(.15)
  if not out:raise RuntimeError('Missing terminal '+title)
  time.sleep(1)
  window=out[0];subprocess.run(['xdotool','windowmove',window,str(x),str(y),'windowsize',window,str(w),str(h)],env=env,check=True)
  time.sleep(.4)
  subprocess.run(['xdotool','windowmove',window,str(x),str(y),'windowsize',window,str(w),str(h)],env=env,check=True)
  return window
 launch_command=([sys.executable,'-c',"import ttools.__main__ as app;app.SPLASH_DURATION=4;app.main()"] if args.startup_preview else [sys.executable,'-m','ttools','--no-splash'])
 launch=terminal('ttools',launch_command,55,65,1810 if (args.startup_preview or args.launcher_preview) else 1010,930 if (args.startup_preview or args.launcher_preview) else 650)
 if args.startup_preview or args.launcher_preview:
  time.sleep(1.15)
  shot=root.get_image(0,0,1920,1080,X.ZPixmap,0xffffffff)
  Image.frombytes('RGB',(1920,1080),shot.data,'raw','BGRX').save(ASSETS/('startup-desktop.png' if args.startup_preview else 'workspace-05-minimal.png'))
  raise SystemExit(0)
 spotify=next(a for a in apps if a['id']=='tspotify')
 music_env=dict(spotify['env'],TSPOTIFY_INSTALL_PREFIX=str(folder/'standalone-spotify'))
 (folder/'standalone-spotify').mkdir()
 music=terminal('tspotify',spotify['command'],1090,100,780,560,music_env)
 things=terminal('tthings',[sys.executable,'-m','tthings','--effect','phyllotaxis'],890,690,720,310,{'PYTHONPATH':str(ROOT/'components/tthings/source')})
 time.sleep(3)
 for window in (launch,music,things):subprocess.run(['xdotool','windowraise',window],env=env)
 time.sleep(1)
 connection=display.Display(':77');root=connection.screen().root
 def capture():
  data=root.get_image(0,0,1920,1080,X.ZPixmap,0xffffffff)
  return Image.frombytes('RGB',(1920,1080),data.data,'raw','BGRX')
 capture().save(ASSETS/'desktop.png')
 frames=[]
 subprocess.run(['xdotool','windowactivate',launch],env=env)
 for i in range(32):
  if i in (4,8,12,24,28):subprocess.run(['xdotool','key',{4:'Down',8:'Up',12:'Return',24:'ctrl+q',28:'n'}[i]],env=env)
  frames.append(capture().resize((960,540)));time.sleep(.16)
 frames[0].save(ASSETS/'desktop.gif',save_all=True,append_images=frames[1:],duration=160,loop=0,optimize=True)
 # Solo view stays a real 1920x1080 desktop, including the native window border.
 subprocess.run(['xdotool','windowminimize',music,'windowminimize',things,'windowmove',launch,'210','155','windowsize',launch,'1500','770','windowactivate',launch],env=env);time.sleep(1)
 capture().save(ASSETS/'launcher-desktop.png')
 # Additional genuine 16:9 compositions; only window placement changes.
 def place(window,x,y,w,h):
  subprocess.run(['xdotool','windowmap',window,'windowsize',window,str(w),str(h),'windowmove',window,str(x),str(y),'windowactivate',window],env=env,check=True);time.sleep(.4)
 def hide(*windows):
  for window in windows:subprocess.run(['xdotool','windowminimize',window],env=env)
 def save(name):time.sleep(1);capture().save(ASSETS/name)
 backdrop('music',[(65,100,1130,810),(1250,225,600,580)]);hide(launch);place(music,65,100,1130,810);place(things,1250,225,600,580);save('workspace-02-music.png')
 backdrop('minimal',[(200,140,1500,770)]);hide(music);place(launch,200,140,1500,770);hide(things);save('workspace-05-minimal.png')
 # Telegram is an isolated fixture; the real account and TDLib are never opened.
 Image.open(ASSETS/'ascii-gallery.png').resize((520,300)).save(folder/'poster.png')
 telegram=terminal('ttelegram',[release/'apps/ttelegram/current/venv/bin/python',ROOT/'tools/media_telegram_fixture.py'],1000,70,850,600,{'TTOOLS_MEDIA_DIR':str(folder),'TTELEGRAM_TEST_RUNTIME':str(ROOT/'components/ttelegram/source')})
 subprocess.run(['xdotool','windowactivate',telegram,'key','Return'],env=env);time.sleep(2)
 backdrop('daily',[(55,100,1000,810),(1100,100,765,670)]);hide(launch);place(music,55,100,1000,810);place(telegram,1100,100,765,670);save('workspace-04-daily.png')
 vpn=terminal('TVPN',[sys.executable,ROOT/'tools/demo_vpn.py'],1055,610,810,400,font=8)
 backdrop('collection',[(55,110,955,860),(1055,110,810,860)]);hide(telegram);place(music,55,110,955,860);place(vpn,1055,110,810,860);save('workspace-01-collection.png')
 backdrop('gallery',[(55,160,850,650),(970,160,850,650)]);hide(music,telegram,vpn);place(things,55,160,850,650)
 rose=terminal('tthings / rose',[sys.executable,'-m','tthings','--effect','rose'],970,160,850,650,{'PYTHONPATH':str(ROOT/'components/tthings/source')});save('workspace-03-gallery.png')
 backdrop('experimental',[(70,80,1040,750),(1170,360,680,610)]);hide(rose);place(launch,70,80,1040,750);place(things,1170,360,680,610);save('workspace-06-experimental.png')
 # Large, native individual interfaces for the README app sections.
 hide(launch,things,music,telegram,vpn)
 backdrop('music',[(85,95,1750,875)])
 (folder/'solo-spotify').mkdir()
 solo_env=dict(music_env,TSPOTIFY_INSTALL_PREFIX=str(folder/'solo-spotify'))
 music_solo=terminal('tspotify',spotify['command'],85,95,1750,875,solo_env,font=14)
 save('app-spotify.png')
 subprocess.run(['xdotool','key','F3'],env=env);time.sleep(.5);save('app-spotify-player.png')
 subprocess.run(['xdotool','key','F3'],env=env);hide(music_solo)
 backdrop('daily',[(85,95,1750,875)])
 hide(telegram)
 telegram_solo=terminal('ttelegram',[release/'apps/ttelegram/current/venv/bin/python',ROOT/'tools/media_telegram_fixture.py'],85,95,1750,875,{'TTOOLS_MEDIA_DIR':str(folder),'TTELEGRAM_TEST_RUNTIME':str(ROOT/'components/ttelegram/source')},font=14)
 subprocess.run(['xdotool','windowactivate',telegram_solo,'key','Return'],env=env);time.sleep(.5)
 subprocess.run(['xdotool','type','--clearmodifiers','--delay','3','Оставляем этот вариант. Подберём музыку?'],env=env)
 save('app-telegram.png');hide(telegram_solo)
 backdrop('collection',[(85,95,1750,875)])
 vpn_solo=terminal('TVPN / обзор карты',[sys.executable,ROOT/'tools/demo_vpn.py'],85,95,1750,875,font=14)
 save('app-vpn.png');hide(vpn_solo)
 backdrop('gallery',[(85,95,1750,875)])
 place(things,85,95,1750,875);save('app-tthings.png')
 print('Native desktop captures saved. Logs:',folder,flush=True)
finally:
 for p in reversed(children):
  if p.poll() is None:p.terminate()
 for p in children:
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill()
