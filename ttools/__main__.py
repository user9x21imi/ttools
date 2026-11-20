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

def selection_pairs(app_id):
    key = app_id.casefold()
    if key.startswith('t') and key[1:] in APP_STYLES:
        key = key[1:]
    if key not in APP_STYLES:
        return 6, 5
    index = list(APP_STYLES).index(key)
    return 9 + index*2, 10 + index*2

DESCRIPTIONS = {'tvpn':'Защищённое соединение', 'tspotify':'Музыка и ваша библиотека', 'ttelegram':'Сообщения и каналы', 'tthings':'Эффекты и системные инструменты'}

class UI:
    def __init__(self, screen, splash=True, motion=True, effect=None, low_power=False):
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
        self.background=Background(motion=motion,effect=effect,low_power=low_power)
        self.effect=self.background.effect
        self._paint_cache={}
        self.colors()
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

    def colors(self):
        curses.start_color()
        curses.use_default_colors()
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
        self.s.bkgd(' ', curses.color_pair(1))

    def put(self,y,x,text,pair=1,bold=False):
        h,w=self.s.getmaxyx()
        if 0<=y<h and 0<=x<w-1:
            for offset,char in enumerate(str(text)[:w-x-1]):
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
        self.s.refresh()

    def check_updates(self):
        for app in self.apps:
            if app['id'] not in self.jobs:
                self.jobs[app['id']] = self.pool.submit(check_update, dict(app))
                self.updates[app['id']] = 'Проверка…'
        self.last_check = time.monotonic()

    def filtered(self):
        return [a for a in self.apps if self.query.casefold() in (a.get('name',a['id'])+' '+a['id']).casefold()]

    def draw(self):
        now = time.monotonic()
        for app_id, job in list(self.jobs.items()):
            if job.done():
                self.updates[app_id] = job.result()
                del self.jobs[app_id]
        if now-self.last_check > 3600:
            self.check_updates()
        self._pending={}
        h,w = self.s.getmaxyx()
        if getattr(self,'_last_size',None)!=(h,w):
            self.s.erase();self._paint_cache={};self._last_size=(h,w)
        if h < 18 or w < 64:
            self.put(0,0,'ttools · увеличьте терминал до 64 × 18',3)
            self.put(2,0,'Q — выход')
            self.flush()
            return
        frame=self.background.render(w-2,h,now)
        self.effect=self.background.effect
        ox=max(0,(w-frame.w)//2);oy=max(0,(h-frame.h)//2)
        age=now-self.started
        showing_splash=self.splash and age<SPLASH_DURATION
        left=max(3,round(w*.045))
        roomy=w>=100 and h>=34
        menu_width=min(62,max(42,round(w*.47))) if w>=100 else min(104,w-left*2)
        for y,row in enumerate(frame.cells):
            for x,(char,color) in enumerate(row):
                sx,sy=x+ox,y+oy
                quiet=(not showing_splash and 2<=sy<h-5 and left<=sx<left+menu_width)
                if char!=' ' and not quiet:self.put(sy,sx,char,8 if color=='#c96a98' else 7)
        if showing_splash:
            width=max(24,min(84,round(w*.42)))
            lines=wordmark(width)
            top=max(2,round(h*.075))
            shade=1
            for i,line in enumerate(lines):self.put(top+i,left,line,shade)
            text_y=min(h-9,top+len(lines)+max(1,h//20))
            self.put(text_y,left,'Всё важное',1,True)
            self.put(text_y+2,left,'в вашем терминале.',1,True)
            self.put(h-5,left,'─'*max(1,w-left*2-1),2)
            self.put(h-3,left,'TTOOLS / ASCII WORKSPACE',1)
            self.put(h-3,max(left,w-left-19),'200 FX + 19 TOOLS',4)
            self.flush()
            return
        width=menu_width
        header=wordmark(min(58,width-2,max(20,int((h-26)/.19)))) if roomy else ()
        extra=max(7,len(header)-1) if roomy else 0
        if roomy:
            for row,line in enumerate(header):self.put(2+row,left,line,1)
        else:self.put(2,left,'tTools_',1,True)
        self.put(2,max(left+width+2,w-24),time.strftime('%H:%M')+' / КОЛЛЕКЦИЯ',2)
        self.put(4+extra,left,'Всё важное в вашем терминале.',1,True)
        if not roomy:self.put(5,left,'Музыка, сообщения и немного движения.',2)
        self.put(7+extra,left,('⌕ '+(self.query or 'Поиск приложений…')+(' ▏' if self.searching else ''))[:width-1],4)
        self.put(9+extra,left,'ПРИЛОЖЕНИЯ / '+str(len(self.apps)).zfill(2),2,True)
        apps = self.filtered()
        self.selected = min(self.selected,max(0,len(apps)-1))
        count = max(1,(h-15-extra)//3)
        start = max(0,self.selected-count+1)
        self.visible = []
        for offset,app in enumerate(apps[start:start+count]):
            index = start+offset
            y = 11+extra+offset*3
            selected = index == self.selected
            accent_pair, row_pair = selection_pairs(app['id'])
            self.visible.append((y,index))
            if selected:
                self.put(y,left,' '*width,row_pair)
                self.put(y+1,left,' '*width,row_pair)
            title = app.get('name',app['id'])
            ready = available(app)
            self.put(y,left+1,('▎ ' if selected else '  ')+f'{index+1:02}  '+title,accent_pair if selected else 1,True)
            badge = 'ENTER  →' if selected and ready else ('НЕТ КОМАНДЫ' if not ready else 'ГОТОВО')
            self.put(y,left+width-len(badge)-2,badge,accent_pair if selected else 2)
            detail=DESCRIPTIONS.get(app['id'],app.get('description','Приложение'))
            update=self.updates.get(app['id'],'')
            if app.get('suite_managed'):update='v'+app.get('version','')
            elif update.startswith('Проверка недоступна'):update='Не проверено'
            elif update=='Нет источника обновлений':update='—'
            update=update[:max(1,width//2-2)]
            update_x=left+width-len(update)-2
            limit=max(1,update_x-left-9)
            if len(detail)>limit:detail=detail[:max(0,limit-1)]+'…'
            self.put(y+1,left+7,detail,row_pair if selected else 2)
            self.put(y+1,update_x,update,row_pair if selected else 2)
        if not apps:
            self.put(11+extra,left,'Ничего не найдено' if self.apps else 'Подключите папку: ttools --import ПУТЬ',2)
        self.put(h-4,left,self.status[:width],4)
        self.put(h-2,left,'↑↓ выбор  Enter запуск  / поиск  U обновления  R каталог  Q выход',2)
        self.put(h-1,left,'N сменить фон  Space '+('продолжить' if self.background.paused else 'пауза'),2)
        self.flush()

    def launch(self,app):
        if not available(app):
            self.status = f"Не найдена команда: {app['command'][0]}"
            return
        self.status = f"{app.get('name',app['id'])} завершён"
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

    def run(self):
        try:
            while True:
                self.draw()
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
                    elif isinstance(key,str) and key.isprintable():
                        self.query += key
                        self.selected = 0
                    continue
                if key in ('q','Q','й','Й','\x11','\x1b'):
                    return
                if key in (curses.KEY_UP,'k'):
                    self.selected = max(0,self.selected-1)
                elif key in (curses.KEY_DOWN,'j'):
                    self.selected = min(max(0,len(self.filtered())-1),self.selected+1)
                elif key == '/':
                    self.searching = True
                elif key==' ':
                    self.background.toggle()
                elif key in ('n','N','т','Т'):
                    self.new_effect()
                elif key in ('u','U','г','Г'):
                    self.check_updates()
                elif key in ('r','R','к','К'):
                    self.apps,self.errors = load_apps()
                    self.status = self.errors[0] if self.errors else 'Каталог перечитан'
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
                                self.selected = index
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
            curses.wrapper(lambda screen: UI(screen,not args.no_splash,not args.no_motion,args.background,args.low_power).run())
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
