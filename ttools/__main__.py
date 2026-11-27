import argparse
import curses
from concurrent.futures import ThreadPoolExecutor
import json
import locale
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
try:
    import termios
except ImportError:
    termios = None
import time

from .core import add_source, available, check_update, load_apps
from .appearance import konsole_profile
from .brand import logo as wordmark
SPLASH_DURATION=1.35
from .backgrounds import Background, Scene, PREFERRED

EFFECTS = list(PREFERRED)
# Per-app accents; all backgrounds follow the terminal default.
APP_STYLES = {
    'spotify': (42, -1, curses.COLOR_GREEN),
    'soundcloud': (208, -1, curses.COLOR_YELLOW),
    'youtube': (196, -1, curses.COLOR_RED),
    'telegram': (75, -1, curses.COLOR_BLUE),
    'vpn': (141, -1, curses.COLOR_MAGENTA),
    'things': (199, -1, curses.COLOR_MAGENTA),
}
APP_RAMP_BASE=32
APP_RAMP_LEVELS=4
ASCII_DESCRIPTIONS={'tspotify':'Music and your library','tsoundcloud':'SoundCloud and track comments','ttelegram':'Messages and channels','tvpn':'Secure connection','tthings':'Effects and system tools'}

def style_key(app_id):
    key=app_id.casefold()
    if key.startswith('t') and key[1:] in APP_STYLES:key=key[1:]
    return key if key in APP_STYLES else 'things'

def ramp_pair(app_id,level):
    index=list(APP_STYLES).index(style_key(app_id))
    return APP_RAMP_BASE+index*APP_RAMP_LEVELS+max(0,min(APP_RAMP_LEVELS-1,int(level)))

def layout_for(width,height):
    """Return the responsive content geometry, hiding art before applications."""
    wide=width>=116 and height>=30
    if wide:
        left=4;nav_x=max(34,round(width*.30));nav_width=min(42,max(28,round(width*.25)))
        art_x=nav_x+nav_width+4
        return {'wide':True,'left':left,'nav_x':nav_x,'nav_width':max(20,min(nav_width,width-nav_x-3)),
                'art_x':art_x,'art_y':6,'art_width':max(1,width-art_x-4),'art_height':max(1,height-13),
                'row_y':9,'row_step':3,'bottom':height-4}
    return {'wide':False,'left':4,'nav_x':4,'nav_width':max(1,width-8),'art_x':width,
            'art_y':0,'art_width':0,'art_height':0,'row_y':7,'row_step':2,'bottom':height-4}

def _xterm_rgb(index):
    base=[(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),(0,128,128),(192,192,192),
          (128,128,128),(255,0,0),(0,255,0),(255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
    if index<16:return base[index]
    if index>=232:
        value=8+(index-232)*10;return value,value,value
    n=index-16;steps=(0,95,135,175,215,255)
    return steps[n//36],steps[(n//6)%6],steps[n%6]

def _nearest_xterm(rgb):
    choices=range(16,256)
    return min(choices,key=lambda i:sum((a-b)**2 for a,b in zip(rgb,_xterm_rgb(i))))

def ascii_status(status):
    if status=='Готово к запуску':return 'Ready to launch'
    if status=='Каталог перечитан':return 'Catalog reloaded'
    if status=='Обновления проверены':return 'App updates checked'
    if status.startswith('Проверка обновлений'):return 'Checking app updates...'
    if status.startswith('Не найдена команда'):return 'Command not found'
    if status.startswith('Ошибка запуска'):return 'Launch failed'
    if 'завершён' in status:return 'Application returned'
    return status if status.isascii() else 'Launcher status'

def selection_pairs(app_id):
    key = app_id.casefold()
    if key.startswith('t') and key[1:] in APP_STYLES:
        key = key[1:]
    if key not in APP_STYLES:
        return 6, 5
    index = list(APP_STYLES).index(key)
    return 9 + index*2, 10 + index*2

DESCRIPTIONS = {'tvpn':'Защищённое соединение', 'tspotify':'Музыка и ваша библиотека', 'tsoundcloud':'SoundCloud и комментарии к трекам', 'ttelegram':'Сообщения и каналы', 'tthings':'Эффекты и системные инструменты'}

class UI:
    def __init__(self, screen, splash=True, motion=True, effect=None, low_power=False, ascii_mode=False):
        self.s = screen
        self.apps, self.errors = load_apps()
        self.selected = 0
        self.query = ''
        self.searching = False
        self.status = self.errors[0] if self.errors else 'Готово к запуску'
        self.updates = {}
        self.jobs = {}
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.started = time.monotonic()
        self.splash = splash
        self.motion_enabled=motion
        self.ascii_mode=ascii_mode
        self.help_open=False
        self.launching=None
        self.return_started=None
        self.selection_from=0.
        self.selection_started=self.started-.12
        self.selection_duration=.12
        self.background=Background(motion=motion,effect=effect,low_power=low_power)
        self.effect=self.background.effect
        self._paint_cache={}
        self.colors()
        if self.apps:self.background.set_accent(style_key(self.apps[0]['id']),self.started,animate=False)
        self.s.timeout(80)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        self.check_updates()

    def new_effect(self):
        self.background.change()
        self.effect=self.background.effect

    def toggle_motion(self):
        if not self.motion_enabled:
            self.background.paused=True
            return
        self.background.toggle()

    def colors(self):
        curses.start_color()
        # Default foreground/background follow the terminal's own theme; on
        # Windows PDCurses this call may be unsupported, so degrade gracefully.
        try:
            curses.use_default_colors()
            self._has_default_colors = True
        except curses.error:
            self._has_default_colors = False
        # Default foreground/background follow the terminal's own light/dark theme.
        # Never switch profiles or redefine the terminal's palette.
        if curses.COLORS>=256:
            pairs=[(-1,-1),(245,-1),(42,-1),(69,-1),
                   (-1,-1),(42,-1),(69,-1),(132,-1)]
        else:
            pairs=[(-1,-1),(-1,-1),(2,-1),(4,-1),
                   (-1,-1),(2,-1),(4,-1),(5,-1)]
        for idx,(fg,bg) in enumerate(pairs,1):curses.init_pair(idx,fg,bg)
        for index,(accent,_,fallback) in enumerate(APP_STYLES.values()):
            fg=accent if curses.COLORS>=256 else fallback
            curses.init_pair(9+index*2,fg,-1)
            curses.init_pair(10+index*2,-1,-1)
            neutral=_xterm_rgb(245)
            target=_xterm_rgb(accent)
            for level,mix in enumerate((.16,.36,.65,1.)):
                rgb=tuple(round(a+(b-a)*mix) for a,b in zip(neutral,target))
                color=_nearest_xterm(rgb) if curses.COLORS>=256 else fallback
                curses.init_pair(ramp_pair(list(APP_STYLES)[index],level),color,-1)
        # Never call bkgd(): painting an explicit window background would cover
        # terminal transparency/acrylic and background images.  The differential
        # painter in flush() only draws foreground characters on -1 backgrounds.

    def put(self,y,x,text,pair=1,bold=False):
        h,w=self.s.getmaxyx()
        text=str(text)
        if getattr(self,'ascii_mode',False):text=text.encode('ascii','replace').decode()
        if 0<=y<h and 0<=x<w-1:
            for offset,char in enumerate(text[:w-x-1]):
                self._pending[(y,x+offset)]=(char,pair,bold)

    def flush(self):
        previous=getattr(self,'_paint_cache',{})
        current=self._pending
        changed=sorted(key for key in previous.keys()|current.keys() if previous.get(key)!=current.get(key))
        index=0
        while index<len(changed):
            y,x=changed[index];char,pair,bold=current.get((y,x),(' ',1,False));text=char;index+=1
            while index<len(changed):
                ny,nx=changed[index];cell=current.get((ny,nx),(' ',1,False))
                if ny!=y or nx!=x+len(text) or cell[1:]!=(pair,bold):break
                text+=cell[0];index+=1
            try:self.s.addnstr(y,x,text,len(text),curses.color_pair(pair)|(curses.A_BOLD if bold else 0))
            except curses.error:pass
        self._paint_cache=current.copy()
        if changed or getattr(self,'_needs_refresh',False):
            self.s.refresh()
            self._needs_refresh=False

    def selection_position(self,now=None):
        now=time.monotonic() if now is None else now
        target=float(self.selected)
        if not getattr(self,'motion_enabled',True):return target
        duration=getattr(self,'selection_duration',.12)
        t=max(0.,min(1.,(now-getattr(self,'selection_started',now))/duration))
        t=t*t*(3.-2.*t)
        return getattr(self,'selection_from',target)+(target-getattr(self,'selection_from',target))*t

    def select(self,index,now=None):
        now=time.monotonic() if now is None else now
        apps=self.filtered()
        index=max(0,min(int(index),max(0,len(apps)-1)))
        changed=index!=self.selected
        if changed:
            self.selection_from=self.selection_position(now)
            self.selected=index
            self.selection_started=now
        if apps:
            setter=getattr(self.background,'set_accent',None)
            if setter:setter(style_key(apps[index]['id']),now,animate=getattr(self,'motion_enabled',True))

    def _timeout(self,now):
        if getattr(self,'splash',False):
            remaining=SPLASH_DURATION-(now-self.started)
            if remaining>0:return max(1,min(100,round(remaining*1000)))
            self.splash=False
        selection_started=getattr(self,'selection_started',now)
        return_started=getattr(self,'return_started',None)
        if getattr(self,'motion_enabled',True) and (now-selection_started<getattr(self,'selection_duration',.12) or
                                    return_started is not None and now-return_started<.12):
            return 33
        if getattr(self,'motion_enabled',True) and not getattr(self.background,'paused',True) and not getattr(self,'help_open',False):
            try:
                h,w=self.s.getmaxyx()
                if layout_for(w,h)['wide']:return round(self.background.FRAME_INTERVAL*1000)
            except (AttributeError,TypeError):pass
        if getattr(self,'jobs',{}):return 200
        # Wake occasionally for the existing hourly update check; static screens
        # do not refresh unless their cell map actually changes.
        return 60000

    def _art_pair(self,color,x,y,now):
        if color=='primary':return 7
        if color!='secondary':return 8
        mix_fn=getattr(self.background,'accent_mix',None)
        if mix_fn is None:return 8
        previous,current,mix=mix_fn(now)
        old=style_key(previous);new=style_key(current)
        threshold=((x*13+y*7)%32)/32
        chosen=new if threshold<=mix else old
        return ramp_pair(chosen,1)

    def _display_glyph(self,char):
        if self.ascii_mode:
            value=ord(char)
            if 0x2800<=value<=0x28ff:
                density=(value-0x2800).bit_count()
                return ' ' if density==0 else '.' if density<=2 else ':' if density<=4 else '*' if density<=6 else '#'
            return {'▏':'|','▎':'|','▍':'|','▌':'|','▋':'|','▊':'|','▉':'|','█':'|','→':'>','⌕':'?','…':'...','↑':'^','↓':'v','─':'-'}.get(char,char if ord(char)<128 else '?')
        return char

    def check_updates(self,announce=False):
        for app in self.apps:
            if app['id'] not in self.jobs:
                self.jobs[app['id']] = self.pool.submit(check_update, dict(app))
                self.updates[app['id']] = 'Проверка…'
        self.announce_updates=announce
        if announce:self.status='Checking app updates...' if self.ascii_mode else 'Проверка обновлений…'
        self.last_check = time.monotonic()

    def filtered(self):
        return [a for a in self.apps if self.query.casefold() in (a.get('name',a['id'])+' '+a['id']).casefold()]

    def draw(self):
        now=time.monotonic()
        finished=[]
        for app_id,job in list(self.jobs.items()):
            if job.done():
                self.updates[app_id]=job.result();del self.jobs[app_id];finished.append(app_id)
        if finished and not self.jobs and getattr(self,'announce_updates',False):
            self.status='Обновления проверены' if not self.ascii_mode else 'App updates checked'
            self.announce_updates=False
        if now-self.last_check>3600:self.check_updates()
        self._pending={};h,w=self.s.getmaxyx()
        if getattr(self,'_last_size',None)!=(h,w):
            self.s.erase();self._paint_cache={};self._last_size=(h,w);self._needs_refresh=True
        if h<18 or w<64:
            self.put(0,0,'ttools - enlarge terminal to 64 x 18' if self.ascii_mode else 'ttools · увеличьте терминал до 64 × 18',3)
            self.put(2,0,'Q - quit' if self.ascii_mode else 'Q — выход');self.flush();return
        age=now-self.started
        if self.splash and age>=SPLASH_DURATION:self.splash=False
        showing_splash=self.splash
        geometry=layout_for(w,h)
        if showing_splash or geometry['wide'] and not self.help_open:
            if showing_splash:
                frame=self.background.render(w-2,h,now);ox=max(0,(w-frame.w)//2);oy=max(0,(h-frame.h)//2)
            else:
                frame=self.background.render(geometry['art_width'],geometry['art_height'],now)
                ox=geometry['art_x']+max(0,(geometry['art_width']-frame.w)//2)
                oy=geometry['art_y']+max(0,(geometry['art_height']-frame.h)//2)
            self.effect=self.background.effect
            for y,row in enumerate(frame.cells):
                for x,(char,color) in enumerate(row):
                    if char!=' ':self.put(y+oy,x+ox,self._display_glyph(char),self._art_pair(color,x+ox,y+oy,now))
        if showing_splash:
            left=max(3,round(w*.045));lines=('T T O O L S',) if self.ascii_mode else wordmark(max(24,min(84,round(w*.42))))
            top=max(2,round(h*.075))
            for i,line in enumerate(lines):self.put(top+i,left,line,1,True)
            text_y=min(h-9,top+len(lines)+max(1,h//20))
            self.put(text_y,left,'Everything that matters' if self.ascii_mode else 'Всё важное',1,True)
            self.put(text_y+2,left,'in your terminal.' if self.ascii_mode else 'в вашем терминале.',1,True)
            self.put(h-5,left,('-' if self.ascii_mode else '─')*max(1,w-left*2-1),2)
            self.put(h-3,left,'TTOOLS / ASCII WORKSPACE',1)
            self.put(h-3,max(left,w-left-19),'200 FX + 19 TOOLS',4);self.flush();return
        left=geometry['left'];nav_x=geometry['nav_x'];nav_width=geometry['nav_width'];wide=geometry['wide']
        if wide:
            logo_width=max(20,min(42,nav_x-left-4));lines=('T T O O L S',) if self.ascii_mode else wordmark(logo_width)
            for row,line in enumerate(lines):self.put(5+row,left,line,1,True)
            identity_y=5+len(lines)+2
            self.put(identity_y,left,'Everything in your terminal.' if self.ascii_mode else 'Всё важное в вашем терминале.',1,True)
            self.put(identity_y+2,left,'A SMALL COLLECTION OF TOOLS' if self.ascii_mode else 'НАБОР ИНСТРУМЕНТОВ / TTOOLS',2)
            self.put(h-3,left,'TTOOLS  /  '+time.strftime('%H:%M'),2)
            self.put(2,w-24,time.strftime('%H:%M')+'  /  '+('COLLECTION' if self.ascii_mode else 'КОЛЛЕКЦИЯ'),2)
            heading='APPLICATIONS / '+str(len(self.apps)).zfill(2) if self.ascii_mode else 'ПРИЛОЖЕНИЯ / '+str(len(self.apps)).zfill(2)
            self.put(5,nav_x,heading,2,True);search_y=7
        else:
            self.put(2,left,'TTOOLS / TERMINAL KIT' if self.ascii_mode else 'ttools  /  терминальный набор',1,True)
            self.put(3,left,'A small collection of tools' if self.ascii_mode else 'Всё важное в вашем терминале.',2)
            heading='APPLICATIONS / '+str(len(self.apps)).zfill(2) if self.ascii_mode else 'ПРИЛОЖЕНИЯ / '+str(len(self.apps)).zfill(2)
            self.put(5,nav_x,heading,2,True);search_y=6
        if self.help_open:
            title='KEYS AND COMMANDS' if self.ascii_mode else 'КЛАВИШИ И КОМАНДЫ'
            space_ascii='SPACE       No-op with --no-motion' if not self.motion_enabled else 'SPACE       Pause / resume artwork'
            space_unicode='Space       Неактивен с --no-motion' if not self.motion_enabled else 'Space       Пауза / продолжение фона'
            items=(('UP / DOWN   Move selection','ENTER       Launch app','/           Search apps','U           Check app updates','R           Reload app catalog',space_ascii,'N           Change artwork','Q / ESC     Quit','--no-motion Disable all animation','--low-power Smaller artwork, 4 fps','--ascii     ASCII-safe display') if self.ascii_mode else ('↑ / ↓       Перемещение по списку','Enter       Запустить приложение','/           Поиск приложений','U           Проверить обновления','R           Перечитать каталог',space_unicode,'N           Сменить сцену','Q / Esc     Выход','--no-motion Отключить анимацию','--low-power Уменьшить и замедлить фон','--ascii     ASCII-совместимый вывод'))
            self.put(8,nav_x,title,3,True)
            for row,item in enumerate(items):self.put(10+row,nav_x,item,2)
            self.put(h-3,nav_x,'? / F1 / ESC  '+('Close help' if self.ascii_mode else 'Закрыть справку'),4);self.flush();return
        search_icon='? ' if self.ascii_mode else '⌕ '
        search_text=self.query or ('Search apps...' if self.ascii_mode else 'Поиск приложений…')
        self.put(search_y,nav_x,(search_icon+search_text+(' |' if self.searching else ''))[:nav_width-1],4)
        apps=self.filtered()
        if self.selected>=len(apps) and apps:self.select(len(apps)-1,now)
        elif not apps:self.selected=0
        row_y=geometry['row_y'];row_step=geometry['row_step']
        count=max(1,(geometry['bottom']-row_y+row_step-1)//row_step);start=max(0,self.selected-count+1)
        self.visible=[];visual=self.selection_position(now) if apps else 0.
        accent_markers=' ▏▏▎▎▍▍▌▌'
        for offset,app in enumerate(apps[start:start+count]):
            index=start+offset;y=row_y+offset*row_step;weight=max(0.,1.-abs(index-visual))
            if index==self.selected and self.motion_enabled and self.return_started is not None and now-self.return_started<.12:
                progress=max(0.,min(1.,(now-self.return_started)/.12));progress=progress*progress*(3.-2.*progress)
                weight=min(weight,.48+.52*progress)
            level=0 if weight<.12 else 1 if weight<.36 else 2 if weight<.72 else 3
            pair=ramp_pair(app['id'],level);self.visible.append((y,index))
            marker='|' if self.ascii_mode else accent_markers[min(8,round(weight*8))]
            label='tsoundcloud' if app['id']=='tsoundcloud' else app.get('name',app['id'])
            line=f'{marker}  {index+1:02}  {label}'
            if self.ascii_mode:line=line.encode('ascii','replace').decode()
            self.put(y,nav_x,line[:nav_width-1],pair,weight>=.72)
            if weight>.42 and y+1<geometry['bottom']:
                detail=ASCII_DESCRIPTIONS.get(app['id'],app.get('description','Application')) if self.ascii_mode else DESCRIPTIONS.get(app['id'],app.get('description','Приложение'))
                if self.launching==app['id']:detail='Launching...' if self.ascii_mode else 'Запуск…'
                elif not available(app):detail='Command not found' if self.ascii_mode else 'Команда не найдена'
                self.put(y+1,nav_x+5,detail[:max(0,nav_width-6)],2)
        if not apps:
            empty=('No matches' if self.ascii_mode else 'Совпадений нет') if self.query else ('Import a folder: ttools --import PATH' if self.ascii_mode else 'Подключите папку: ttools --import ПУТЬ')
            self.put(row_y,nav_x,empty,2)
        status=ascii_status(self.status) if self.ascii_mode else self.status
        status_width=max(1,nav_x-left) if wide else nav_width
        self.put(h-3,left if wide else nav_x,status[:status_width],4)
        keys='UP/DOWN move  ENTER open  / find  ? help  Q quit' if self.ascii_mode else '↑↓ выбор   Enter запуск   / поиск   ? команды   Q выход'
        self.put(h-1,nav_x,keys[:(w-nav_x-1 if wide else nav_width-1)],2)
        if wide:
            left_keys=('N scene  ·  Space inactive' if not self.motion_enabled else 'N scene  ·  Space pause') if self.ascii_mode else ('N сцена  ·  Space неактивен' if not self.motion_enabled else 'N сцена  ·  Space пауза')
            self.put(h-1,left,left_keys,2)
        self.flush()

    def launch(self,app):
        if not available(app):
            self.status = f"Не найдена команда: {app['command'][0]}"
            return
        self.status = f"{app.get('name',app['id'])} завершён"
        self.launching=app['id']
        self.draw()
        curses.def_prog_mode()
        curses.endwin()
        child = None
        previous = {}
        try:
            # Child owns the existing terminal, including its own resize and shortcuts.
            fd = sys.stdin.fileno()
            if termios is not None:
                attrs = termios.tcgetattr(fd)
                attrs[0] &= ~termios.IXON
                termios.tcsetattr(fd,termios.TCSANOW,attrs)
            child = subprocess.Popen(app['command'],env=dict(os.environ,**app.get('env',{})))
            requested = None
            def stop(signum, frame):
                nonlocal requested
                if requested is None:
                    requested = signum
                    if child.poll() is None:
                        try:child.send_signal(signum)
                        except ProcessLookupError:pass
            for sig in (signal.SIGTERM, *([signal.SIGHUP] if hasattr(signal,"SIGHUP") else [])):
                previous[sig] = signal.signal(sig,stop)
            while True:
                try:
                    code = child.wait()
                    if requested is not None:raise SystemExit(128+requested)
                    break
                except KeyboardInterrupt:
                    # The foreground child also receives SIGINT and decides how to handle it.
                    continue
            if code:
                print(f'\nttools: процесс завершился с кодом {code}. Enter — вернуться.')
                input()
                self.status = f"{app['id']}: код выхода {code}"
        except OSError as e:
            self.status = f'Ошибка запуска: {e}'
        finally:
            for sig, handler in previous.items():
                signal.signal(sig,handler)
            curses.reset_prog_mode()
            self.colors()
            self.s.timeout(80)
            self.s.keypad(True)
            curses.flushinp()
            self.s.clear()
            self._paint_cache={}
            self.launching=None
            self.return_started=time.monotonic()
            self.s.timeout(self._timeout(self.return_started))

    def run(self):
        try:
            while True:
                self.draw()
                self.s.timeout(self._timeout(time.monotonic()))
                try:
                    key = self.s.get_wch()
                except curses.error:
                    continue
                if self.splash and time.monotonic()-self.started<SPLASH_DURATION and key not in ('q','Q','й','Й','\x11','\x1b',curses.KEY_RESIZE):
                    self.splash=False
                    continue
                if self.searching:
                    if key in ('\n','\r','\x1b'):
                        self.searching = False
                    elif key in (curses.KEY_BACKSPACE,'\x7f','\b'):
                        self.query = self.query[:-1]
                        self.select(min(self.selected,max(0,len(self.filtered())-1)))
                    elif isinstance(key,str) and key.isprintable():
                        self.query += key
                        self.select(0)
                    continue
                if key in ('?','\x1b',curses.KEY_F1) and self.help_open:
                    self.help_open=False
                    continue
                if key in ('?','\x1b',curses.KEY_F1) and key!='\x1b':
                    self.help_open=True
                    continue
                if key in ('q','Q','й','Й','\x11','\x1b'):
                    return
                if key in (curses.KEY_UP,'k'):
                    self.select(max(0,self.selected-1))
                elif key in (curses.KEY_DOWN,'j'):
                    self.select(min(max(0,len(self.filtered())-1),self.selected+1))
                elif key == '/':
                    self.searching = True
                elif key==' ':
                    self.toggle_motion()
                elif key in ('n','N','т','Т'):
                    self.new_effect()
                elif key in ('u','U','г','Г'):
                    self.check_updates(announce=True)
                elif key in ('r','R','к','К'):
                    self.apps,self.errors = load_apps()
                    self.status = self.errors[0] if self.errors else 'Каталог перечитан'
                    self.select(min(self.selected,max(0,len(self.filtered())-1)))
                    self.check_updates()
                elif key in ('\n','\r',curses.KEY_ENTER):
                    apps = self.filtered()
                    if apps:
                        self.launch(apps[self.selected])
                elif key == curses.KEY_MOUSE:
                    try:
                        _,x,y,_,state = curses.getmouse()
                        for row,index in getattr(self,'visible',[]):
                            if row <= y <= row+1:
                                self.select(index)
                                if state & curses.BUTTON1_DOUBLE_CLICKED:
                                    self.launch(self.filtered()[index])
                    except curses.error:
                        pass
        finally:
            self.pool.shutdown(wait=False,cancel_futures=True)


def main():
    from .distribution import configure_text_io
    configure_text_io()
    parser = argparse.ArgumentParser(description='ttools — единый терминальный клиент')
    parser.add_argument('--import',dest='catalog',help='Подключить папку или apps.local.json')
    parser.add_argument('--list',action='store_true',help='Показать приложения без интерфейса')
    parser.add_argument('--check-updates',action='store_true')
    parser.add_argument('--no-splash',action='store_true')
    parser.add_argument('--background',choices=EFFECTS,help='Выбрать спокойную сцену tthings')
    parser.add_argument('--low-power',action='store_true',help='Меньше область фона и не более 4 кадров/с')
    parser.add_argument('--no-motion',action='store_true',help='Оставить фон неподвижным')
    parser.add_argument('--ascii',action='store_true',help='ASCII-safe labels and artwork fallback')
    from . import __version__
    parser.add_argument('--version',action='version',version=__version__)
    args = parser.parse_args()
    if args.catalog:
        try:
            add_source(args.catalog)
        except (OSError,ValueError,TypeError) as e:
            parser.error(str(e))
        print('Каталог подключён. R в клиенте перечитает изменения.')
        return
    if args.list or args.check_updates:
        apps,errors = load_apps()
        for app in apps:
            print(f"{app['id']:12} {'готово' if available(app) else 'нет команды'}" + (' · '+check_update(app) if args.check_updates else ''))
        for error in errors:
            print(error,file=sys.stderr)
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('Нужен терминал. Используйте ttools --list для вывода без TTY.',file=sys.stderr)
        raise SystemExit(1)
    locale.setlocale(locale.LC_ALL,'')
    try:
        with konsole_profile():
            curses.wrapper(lambda screen: UI(screen,not args.no_splash,not args.no_motion,args.background,args.low_power,args.ascii).run())
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
