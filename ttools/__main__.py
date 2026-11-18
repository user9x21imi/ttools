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
from .visuals.effects import Scene

EFFECTS = ['stars', 'snow', 'rain', 'particles', 'matrix', 'pipes', 'sakura', 'aquarium', 'donut']
LOGO = [
    '        ████████                ██         ',
    ' ▀▄        ██                   ██         ',
    '   ▀▄      ██   ▄████▄  ▄████▄  ██  ▄█████ ',
    '    ▄▀  █  ██   ██  ██  ██  ██  ██  ▀██▄   ',
    '  ▄▀   ▀█▀ ██   ██  ██  ██  ██  ██     ▀██ ',
    ' ▀      █  ██   ▀████▀  ▀████▀  ██  █████▀ ',
    '        ▀▄▄━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ',
]
# Per-app selection: accent, a dark tinted background, and basic-color fallback.
APP_STYLES = {
    'spotify': (42, 22, curses.COLOR_GREEN),
    'soundcloud': (208, 94, curses.COLOR_YELLOW),
    'youtube': (196, 52, curses.COLOR_RED),
    'telegram': (75, 17, curses.COLOR_BLUE),
    'vpn': (141, 54, curses.COLOR_MAGENTA),
    'things': (199, 53, curses.COLOR_MAGENTA),
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
    def __init__(self, screen, splash=True):
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
        self.new_effect()
        self.colors()
        self.s.timeout(60)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        self.check_updates()

    def new_effect(self):
        choices = [n for n in EFFECTS if n != getattr(self, 'effect', '')]
        self.effect = random.choice(choices)
        self.scene = Scene(self.effect)
        self.effect_start = time.monotonic()
        self.next_effect = self.effect_start + random.uniform(30, 120)

    def colors(self):
        curses.start_color()
        curses.use_default_colors()
        # Explicit indexed RGB palette: never redefine ANSI colors with OSC 4.
        # Default background (-1) lets Konsole's compositor opacity show through.
        if curses.COLORS >= 256:
            pairs = [(255,-1),(245,-1),(42,-1),(75,-1),
                     (255,236),(42,236),(235,-1),(237,-1)]
        else:
            pairs = [(7,-1),(7,-1),(2,-1),(6,-1),
                     (7,0),(2,0),(0,-1),(0,-1)]
        for idx, (fg,bg) in enumerate(pairs, 1):
            curses.init_pair(idx, fg,bg)
        for index, (accent, background, fallback) in enumerate(APP_STYLES.values()):
            if curses.COLORS < 256:
                accent, background = fallback, curses.COLOR_BLACK
            curses.init_pair(9+index*2, accent, background)
            curses.init_pair(10+index*2, 255 if curses.COLORS >= 256 else curses.COLOR_WHITE, background)
        self.s.bkgd(' ', curses.color_pair(1))

    def put(self,y,x,text,pair=1,bold=False):
        h,w = self.s.getmaxyx()
        if 0 <= y < h and 0 <= x < w-1:
            try:
                self.s.addnstr(y,x,str(text),w-x-1,curses.color_pair(pair)|(curses.A_BOLD if bold else 0))
            except curses.error:
                pass

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
        if now > self.next_effect:
            self.new_effect()
        for app_id, job in list(self.jobs.items()):
            if job.done():
                self.updates[app_id] = job.result()
                del self.jobs[app_id]
        if now-self.last_check > 3600:
            self.check_updates()
        self.s.erase()
        h,w = self.s.getmaxyx()
        if h < 18 or w < 64:
            self.put(0,0,'ttools · увеличьте терминал до 64 × 18',3)
            self.put(2,0,'Q — выход')
            self.s.refresh()
            return
        # Render real tthings scenes in a small grid; recolor to a muted palette.
        frame = self.scene.render(min(w-2,110),min(h,40),now-self.effect_start)
        ox = max(0,(w-frame.w)//2)
        for y,row in enumerate(frame.cells):
            for x,(ch,_) in enumerate(row):
                if ch != ' ':
                    self.put(y,x+ox,ch,7 if (x+y)%4 else 8)
        age = now-self.started
        if self.splash and age < 1.15:
            shade = 7 if age < .15 or age > 1.02 else (4 if age < .35 else 3)
            for i,line in enumerate(LOGO):
                self.put(h//2-len(LOGO)//2+i,(w-max(map(len,LOGO)))//2,line,shade,True)
            self.put(h//2+len(LOGO)//2+2,(w-21)//2,'YOUR TOOLS. ONE PLACE.',2)
            self.s.refresh()
            return
        left = max(3,(w-104)//2)
        width = min(w-left*2,104)
        self.put(2,left,'> tTools▁',3,True)
        self.put(2,left+width-22,time.strftime('%H:%M')+'  /  WORKSPACE',2)
        self.put(4,left,'Ваши инструменты',1,True)
        self.put(5,left,'Один вход. Всё под рукой.',2)
        self.put(7,left,'⌕  '+(self.query or 'Поиск приложений…')+(' ▏' if self.searching else ''),4)
        self.put(9,left,'БИБЛИОТЕКА',2,True)
        apps = self.filtered()
        self.selected = min(self.selected,max(0,len(apps)-1))
        count = max(1,(h-15)//3)
        start = max(0,self.selected-count+1)
        self.visible = []
        for offset,app in enumerate(apps[start:start+count]):
            index = start+offset
            y = 11+offset*3
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
            detail = DESCRIPTIONS.get(app['id'],app.get('description','Приложение'))
            self.put(y+1,left+7,detail[:max(1,width//2-6)],row_pair if selected else 2)
            self.put(y+1,left+width//2,self.updates.get(app['id'],'')[:width//2-2],row_pair if selected else 2)
        if not apps:
            self.put(11,left,'Ничего не найдено' if self.apps else 'Подключите папку: ttools --import ПУТЬ',2)
        self.put(h-4,left,self.status[:width],4)
        self.put(h-2,left,'↑↓ выбор  Enter запуск  / поиск  U обновления  R каталог  Q выход',2)
        self.put(h-1,left,f'Фон: {self.effect} · N сменить · автосмена 30–120 с',2)
        self.s.refresh()

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
            self.s.timeout(60)
            self.s.keypad(True)
            curses.flushinp()
            self.s.clear()

    def run(self):
        try:
            while True:
                self.draw()
                try:
                    key = self.s.get_wch()
                except curses.error:
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
            curses.wrapper(lambda screen: UI(screen,not args.no_splash).run())
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
