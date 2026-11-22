"""Settings that stay inside the terminal and accept both mouse and keyboard."""
from native_image import synchronized,begin_frame
import curses,json
from pathlib import Path
PATH=Path.home()/'.config/ttelegram/media.json'

def read():
    try:
        value=json.loads(PATH.read_text())
        return value if isinstance(value,dict) else {'mode':'native','quality':'high'}
    except (OSError,ValueError):return {'mode':'native','quality':'high'}

def save(value):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    temp=PATH.with_suffix('.json.tmp');temp.write_text(json.dumps(value));temp.replace(PATH)

class Settings:
    tabs=['Медиа','Оформление','Панели']
    def __init__(self):self.tab=0;self.selected=0;self.buttons=[]
    def options(self):
        if self.tab==0:return [('native','Обычные изображения — фото, стикеры и GIF'),('dots','Точечный стиль DOTS')]
        if self.tab==1:return [('0','Neon — бирюзовый и фиолетовый'),('1','Amber — янтарный'),('2','Mint — мятный')]
        return [('full','Переписка на всё окно'),('sidebar','Список чатов слева от переписки')]
    def current(self):
        import ui
        if self.tab==0:return read().get('mode','native')
        config=ui.state()
        return str(config.get('theme',0)) if self.tab==1 else config.get('layout','sidebar')
    def apply(self,index):
        import ui
        options=self.options()
        if not 0<=index<len(options):return
        key=options[index][0]
        if self.tab==0:
            config=read();config['mode']=key;save(config)
        else:
            config=ui.state();config['theme' if self.tab==1 else 'layout']=int(key) if self.tab==1 else key
            ui.save(config)
            if self.tab==1:ui.style(config)
            else:ui.layout(config)
    @synchronized
    def draw(self,screen):
        from tg.colors import get_color,cyan,bold
        h,w=screen.getmaxyx();begin_frame(screen);screen.erase();self.buttons=[];accent=get_color(cyan,-1)|bold
        def put(y,x,text,attr=0):
            if 0<=y<h and 0<=x<w-1:
                try:screen.addstr(y,x,text[:w-x-1],attr)
                except curses.error:pass
        put(0,2,'ttelegram / НАСТРОЙКИ',accent)
        put(1,2,'Ctrl+O / F4 / Esc — закрыть · мышь или стрелки + Enter')
        x=2
        for index,title in enumerate(self.tabs):
            text='['+title+'] '
            put(3,x,text,accent if index==self.tab else 0)
            self.buttons.append((3,x,x+len(text)-1,('tab',index)));x+=len(text)
        put(3,x,'[Закрыть]',accent);self.buttons.append((3,x,x+9,('close',0)))
        current=self.current()
        for index,(key,label) in enumerate(self.options()):
            y=6+index*3
            text=('> ' if index==self.selected else '  ')+('[●] ' if current==key else '[ ] ')+label
            put(y,2,text,accent if index==self.selected else 0)
            self.buttons.append((y,2,min(w-2,2+len(text)),('option',index)))
        put(h-3,2,'Настройки сохраняются сразу. Исходные файлы собеседнику не изменяются.')
        put(h-2,2,'Ctrl+L — чаты · Ctrl+Q — сохранить и выйти',accent)
        screen.refresh()
    def run(self,screen):
        curses.curs_set(0);curses.mousemask(curses.ALL_MOUSE_EVENTS);screen.keypad(True);screen.timeout(200)
        while True:
            self.draw(screen)
            try:key=screen.get_wch()
            except curses.error:continue
            if key in ('\x1b','\x0f',curses.KEY_F4):return None
            if key in ('\x11','\x0c'):return 'quit' if key=='\x11' else 'chat_list'
            if key in (curses.KEY_RIGHT,'\t'):self.tab=(self.tab+1)%len(self.tabs);self.selected=0
            elif key==curses.KEY_LEFT:self.tab=(self.tab-1)%len(self.tabs);self.selected=0
            elif key==curses.KEY_UP:self.selected=max(0,self.selected-1)
            elif key==curses.KEY_DOWN:self.selected=min(len(self.options())-1,self.selected+1)
            elif key in ('\n','\r',curses.KEY_ENTER):self.apply(self.selected)
            elif key==curses.KEY_MOUSE:
                try:_,x,y,_,buttons=curses.getmouse()
                except curses.error:continue
                if buttons&(curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED):
                    action=next((action for row,left,right,action in self.buttons if y==row and left<=x<right),None)
                    if action:
                        kind,index=action
                        if kind=='close':return None
                        if kind=='tab':self.tab=index;self.selected=0
                        else:self.selected=index;self.apply(index)

def show(controller=None):
    if controller is None:
        from recovery import CURRENT
        controller=CURRENT
    if controller is None:return
    from overlay import open_overlay,run_modal
    with open_overlay(controller,'Настройки · Ctrl+O/Esc — закрыть'):
        result=run_modal(controller,Settings().run)
    if result:controller.view.status.pending_action=result
if __name__=='__main__':show()
