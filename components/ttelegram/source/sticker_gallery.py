"""Visual sticker/GIF picker. Fetches thumbnails in the background; never sends."""
from concurrent.futures import Future
import queue,threading
from native_image import synchronized,begin_frame
import curses
from pathlib import Path
import time
from media import dimensions,still_frame
from native_image import draw as draw_image
from tg.colors import get_color,cyan,bold

TABS=[('Недавние','recent'),('Избранные','favorite'),('Наборы','packs'),('GIF','gifs')]



class PreviewPool:
    """Daemon workers keep a slow thumbnail request from delaying Ctrl+Q."""
    def __init__(self,workers=4):
        self.tasks=queue.Queue();self.stop=threading.Event();self.threads=[]
        for index in range(workers):
            thread=threading.Thread(target=self.worker,daemon=True,name=f'sticker-thumb-{index}')
            thread.start();self.threads.append(thread)
    def worker(self):
        while not self.stop.is_set():
            try:future,fn,args=self.tasks.get(timeout=.1)
            except queue.Empty:continue
            if not future.set_running_or_notify_cancel():continue
            try:future.set_result(fn(*args))
            except BaseException as error:future.set_exception(error)
    def submit(self,fn,*args):
        future=Future();self.tasks.put((future,fn,args));return future
    def shutdown(self,wait=False,cancel_futures=True):
        self.stop.set()
        if cancel_futures:
            while True:
                try:future,_,_=self.tasks.get_nowait();future.cancel()
                except queue.Empty:break
        if wait:
            for thread in self.threads:thread.join(timeout=22)

def image_file(item,kind):
    thumbnail=(item.get('thumbnail') or {}).get('file') or (item.get('thumbnail') or {}).get('photo')
    if thumbnail:return thumbnail
    if kind=='packs':
        covers=item.get('covers') or []
        return image_file(covers[0],'recent') if covers else None
    return item.get('animation') if kind=='gifs' else item.get('sticker')


class Gallery:
    def __init__(self,tg,kind='recent',api=None):
        if api is None:
            from features import request
            api=lambda data:request(tg,data)
        self.api=api;self.kind=kind;self.pool=PreviewPool()
        self.files={};self.items=[];self.selected=0;self.page=0;self.set_id=None
        self.error='';self.loading=None;self.tiles=[];self.buttons=[];self.last_frame=None
        self.load(kind)

    def load(self,kind,set_id=None):
        self.kind=kind;self.set_id=set_id;self.items=[];self.selected=0;self.page=0;self.error='';self.last_frame=None
        if kind=='recent':data={'@type':'getRecentStickers','is_attached':False};field='stickers'
        elif kind=='favorite':data={'@type':'getFavoriteStickers'};field='stickers'
        elif kind=='packs':data={'@type':'getInstalledStickerSets','sticker_type':{'@type':'stickerTypeRegular'}};field='sets'
        elif kind=='gifs':data={'@type':'getSavedAnimations'};field='animations'
        else:data={'@type':'getStickerSet','set_id':set_id};field='stickers'
        self.loading=self.pool.submit(lambda:self.api(data).get(field,[]))

    def preview(self,file):
        path=file.get('local',{}).get('path')
        if not path or not Path(path).is_file():
            loaded=self.api({'@type':'downloadFile','file_id':file['id'],'priority':16,'synchronous':True})
            path=loaded.get('local',{}).get('path')
        if not path or not Path(path).is_file():raise ValueError('Изображение ещё недоступно')
        result=still_frame(path,Path(path).stat().st_mtime_ns)
        if not result:raise ValueError('Не удалось прочитать изображение')
        return result

    def path_for(self,item):
        file=image_file(item,self.kind)
        if not file or not file.get('id'):return None,'Нет обложки'
        key=file['id']
        if key not in self.files:self.files[key]=self.pool.submit(self.preview,file)
        future=self.files[key]
        if not future.done():return None,'Загрузка…'
        try:return future.result(),''
        except Exception:return None,'Не загрузилось · R'

    def geometry(self,height,width):
        cols=max(1,min(6,(width-4)//22));rows=max(1,min(4,(height-8)//12))
        return cols,rows,max(10,(width-4)//cols),max(6,(height-8)//rows)

    @synchronized
    def draw(self,screen):
        h,w=screen.getmaxyx()
        if self.loading and self.loading.done():
            try:self.items=self.loading.result()
            except Exception:self.error='Не удалось загрузить список. R — повторить.'
            self.loading=None;self.last_frame=None
        cols,rows,cw,ch=self.geometry(h,w);per=cols*rows
        pages=max(1,(len(self.items)+per-1)//per);self.page=min(self.page,pages-1)
        chunk=self.items[self.page*per:(self.page+1)*per]
        previews=[self.path_for(item) for item in chunk]
        frame=(h,w,self.kind,self.set_id,self.page,self.selected,len(self.items),self.loading is not None,self.error,tuple(previews))
        if frame==self.last_frame:return
        self.last_frame=frame;begin_frame(screen);screen.erase();self.tiles=[];self.buttons=[]
        accent=get_color(cyan,-1)|bold
        def put(y,x,text,attr=0):
            if 0<=y<h and x<w-1:
                try:screen.addstr(y,x,text[:max(0,w-x-1)],attr)
                except curses.error:pass
        put(0,2,'СТИКЕРЫ И GIF · Картинки · клик — выбрать, Отправить — отправить',accent)
        x=2
        for title,kind in TABS:
            label='['+title+'] '
            put(1,x,label,accent if self.kind==kind or self.kind=='set' and kind=='packs' else 0)
            self.buttons.append((1,x,x+len(label)-1,kind));x+=len(label)
        put(1,x,'[Закрыть]',accent);self.buttons.append((1,x,x+9,'close'))
        if self.loading:put(3,3,'Загружаю изображения…')
        elif self.error:put(3,3,self.error)
        elif not self.items:put(3,3,'Здесь пока пусто. Выберите другую вкладку.' if self.kind!='gifs' else 'Сохранённых GIF пока нет. Можно выбрать GIF с диска.')
        for offset,(item,(path,note)) in enumerate(zip(chunk,previews)):
            index=self.page*per+offset
            y=4+(offset//cols)*ch;x=2+(offset%cols)*cw
            tile_h=min(ch-1,h-y-4);tile_w=min(cw-1,w-x-2)
            if tile_h<4 or tile_w<6:continue
            selected=index==self.selected;attr=accent if selected else curses.A_DIM
            put(y,x,'+'+'-'*(tile_w-2)+'+',attr)
            for line in range(1,tile_h-1):
                put(y+line,x,'|',attr);put(y+line,x+tile_w-1,'|',attr)
            put(y+tile_h-1,x,'+'+'-'*(tile_w-2)+'+',attr)
            if not path:put(y+tile_h//2,x+2,note,attr)
            title=item.get('title','') if self.kind=='packs' else ('Выбрано' if selected else '')
            put(y+tile_h-1,x+2,title[:tile_w-4],attr)
            self.tiles.append((y,x,tile_h,tile_w,index,path))
        x=2
        footer=[('← Назад','previous'),('Вперёд →','next'),('Отправить','send'),('Обновить','refresh'),('Отмена','close')]
        if self.kind=='gifs':footer.insert(2,('GIF с диска','upload'))
        for title,key in footer:
            label='['+title+'] '
            put(h-3,x,label,accent);self.buttons.append((h-3,x,x+len(label)-1,key));x+=len(label)
        put(h-2,2,f'Страница {self.page+1}/{pages} · стрелки — выбор · Enter — отправить · Esc — назад')
        screen.refresh()
        for y,x,th,tw,index,path in self.tiles:
            if not path:continue
            try:
                width,height=dimensions(path,max(1,tw-4),max(1,th-3))
                draw_image(screen,path,y+1+(th-3-height)//2,x+(tw-width)//2,width,height)
            except (OSError,ValueError):put(y+2,x+2,'Ошибка изображения')
        # Leave the cursor away from the images; do not refresh unchanged cells.
        screen.move(0,0)

    def select(self,index):
        self.selected=max(0,min(len(self.items)-1,index))

    def command(self,key,per):
        if key=='close':return ('close',None)
        if key=='refresh':
            self.files={};self.load(self.kind,self.set_id);return
        if key=='previous':self.page=max(0,self.page-1);self.select(self.page*per)
        elif key=='next':self.page+=1;self.select(self.page*per)
        elif key in ('recent','favorite','packs','gifs'):self.load(key)
        elif key=='upload':return ('upload',None)
        elif key=='send' and self.items:
            item=self.items[self.selected]
            if self.kind=='packs':self.load('set',item['id']);return
            path,note=self.path_for(item)
            if path:return ('animation' if self.kind=='gifs' else 'sticker',item)

    def run(self,screen):
        curses.curs_set(0);curses.mousemask(curses.ALL_MOUSE_EVENTS);curses.mouseinterval(150);screen.keypad(True);screen.timeout(80)
        try:
            while True:
                self.draw(screen)
                h,w=screen.getmaxyx();cols,rows,_,_=self.geometry(h,w);per=cols*rows
                try:key=screen.get_wch()
                except curses.error:continue
                result=None
                if key=='\x11':return ('quit',None)
                if key=='\x0c':return ('chats',None)
                if key in ('\x0f',curses.KEY_F4):return ('settings',None)
                if key in ('\x1b','q',curses.KEY_F7):return None
                if key in ('r','R'):result=self.command('refresh',per)
                elif key in ('\n','\r',curses.KEY_ENTER):result=self.command('send',per)
                elif key==curses.KEY_RIGHT:self.select(self.selected+1)
                elif key==curses.KEY_LEFT:self.select(self.selected-1)
                elif key==curses.KEY_DOWN:self.select(self.selected+cols)
                elif key==curses.KEY_UP:self.select(self.selected-cols)
                elif key==curses.KEY_NPAGE:result=self.command('next',per)
                elif key==curses.KEY_PPAGE:result=self.command('previous',per)
                elif key=='\t':self.load(TABS[(next((i for i,t in enumerate(TABS) if t[1]==self.kind),0)+1)%len(TABS)][1])
                elif key==curses.KEY_MOUSE:
                    try:_,x,y,_,buttons=curses.getmouse()
                    except curses.error:continue
                    if buttons & getattr(curses,'BUTTON4_PRESSED',0):result=self.command('previous',per)
                    elif buttons & getattr(curses,'BUTTON5_PRESSED',0):result=self.command('next',per)
                    elif buttons & (curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED|curses.BUTTON1_DOUBLE_CLICKED):
                        button=next((name for row,left,right,name in self.buttons if row==y and left<=x<right),None)
                        if button:result=self.command(button,per)
                        else:
                            tile=next((t for t in self.tiles if t[0]<=y<t[0]+t[2] and t[1]<=x<t[1]+t[3]),None)
                            if tile:
                                self.select(tile[4])
                                if self.kind=='packs':self.command('send',per)
                if result:
                    if result[0]=='close':return None
                    return result
                if self.items:self.page=self.selected//per
        finally:
            screen.timeout(-1);self.pool.shutdown(wait=False,cancel_futures=True)


def pick(controller,kind='recent'):
    from overlay import open_overlay,run_modal
    with open_overlay(controller,'Галерея стикеров и GIF · Esc — назад'):
        gallery=Gallery(controller.tg,kind)
        return run_modal(controller,gallery.run)
