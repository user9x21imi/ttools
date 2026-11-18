"""Native 16:9 demo captures. Xvfb only: never open a window on the host desktop."""
import os,subprocess,time,tempfile,json,shutil,sys
from pathlib import Path
from PIL import Image
from Xlib import display,X
import argparse
parser=argparse.ArgumentParser(description='Capture native Konsole windows in an invisible, isolated Xvfb desktop')
parser.add_argument('--suite-prefix',type=Path,required=True)
parser.add_argument('--xvfb',default=shutil.which('Xvfb'))
args=parser.parse_args()
if not args.xvfb:parser.error('Xvfb is required; no visible Xwayland fallback is used')
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'docs/assets'
if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):parser.error('Run with dbus-run-session -- python tools/capture_workspaces.py ...')
folder=Path(tempfile.mkdtemp(prefix='ttools-desktop-'))
env=dict(os.environ,DISPLAY=':77',QT_QPA_PLATFORM='xcb',LIBGL_ALWAYS_SOFTWARE='1',TERM='xterm-256color',COLORTERM='truecolor')
for name in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','TSPOTIFY_CONFIG_DIR','TSPOTIFY_CACHE_DIR','TSPOTIFY_DATA_DIR'):
 env[name]=str(folder/name);Path(env[name]).mkdir()
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
 wallpaper=Image.new('RGB',(1920,1080),'#deded4')
 pixmap=root.create_pixmap(1920,1080,24);gc=pixmap.create_gc()
 for yy in range(0,1080,20):
  strip=wallpaper.crop((0,yy,1920,min(1080,yy+20)))
  pixmap.put_image(gc,0,yy,1920,strip.height,X.ZPixmap,24,0,strip.tobytes('raw','BGRX'))
 from Xlib import Xatom
 for atom in ('_XROOTPMAP_ID','ESETROOT_PMAP_ID'):root.change_property(connection.intern_atom(atom),Xatom.PIXMAP,32,[pixmap.id])
 root.change_attributes(background_pixmap=pixmap);root.clear_area();connection.sync()
 wallpaper.save(folder/'wallpaper.png')
 wall=start([sys.executable,'-c',"import tkinter as t; r=t.Tk();r.geometry('1920x1080+0+0');r.attributes('-type','desktop');im=t.PhotoImage(file="+repr(str(folder/'wallpaper.png'))+");t.Label(r,image=im,borderwidth=0).pack();r.lower();r.mainloop()"]);time.sleep(1)
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
 def terminal(title,command,x,y,w,h,extra=None):
  p=start(['konsole','--separate','--profile','ttools','--hide-menubar','--hide-tabbar','--hide-toolbars','-p','LocalTabTitleFormat='+title,'-e',*command],extra)
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
 launch=terminal('ttools',[sys.executable,'-m','ttools','--no-splash','--background','light_bloom'],55,65,1010,650)
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
 hide(launch);place(music,65,100,1130,810);place(things,1250,225,600,580);save('workspace-02-music.png')
 hide(music);place(launch,200,140,1500,770);hide(things);save('workspace-05-minimal.png')
 # Telegram is an isolated fixture; the real account and TDLib are never opened.
 Image.open(ASSETS/'ascii-gallery.png').resize((520,300)).save(folder/'poster.png')
 telegram=terminal('ttelegram',[release/'apps/ttelegram/current/venv/bin/python',ROOT/'tools/media_telegram_fixture.py'],1000,70,850,600,{'TTOOLS_MEDIA_DIR':str(folder),'TTELEGRAM_TEST_RUNTIME':str(ROOT/'components/ttelegram/source')})
 subprocess.run(['xdotool','windowactivate',telegram,'key','Return'],env=env);time.sleep(2)
 hide(launch);place(music,55,100,1000,810);place(telegram,1100,100,765,670);save('workspace-04-daily.png')
 vpn=terminal('TVPN',[sys.executable,ROOT/'tools/demo_vpn.py'],1050,655,810,360)
 hide(telegram);place(music,55,65,955,900);place(vpn,1055,65,810,900);save('workspace-01-collection.png')
 hide(music,telegram,vpn);place(things,55,160,850,650)
 rose=terminal('tthings / rose',[sys.executable,'-m','tthings','--effect','rose'],970,160,850,650,{'PYTHONPATH':str(ROOT/'components/tthings/source')});save('workspace-03-gallery.png')
 hide(rose);place(launch,70,80,1040,750);place(things,1170,360,680,610);save('workspace-06-experimental.png')
 print('Native desktop captures saved. Logs:',folder,flush=True)
finally:
 for p in reversed(children):
  if p.poll() is None:p.terminate()
 for p in children:
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill()
