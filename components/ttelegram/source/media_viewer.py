"""Full-window native media with sender, timestamp, caption and original-file actions."""
from native_image import synchronized,begin_frame
import curses,hashlib,os,shutil,subprocess,sys,textwrap,time
from datetime import datetime
from pathlib import Path
from PIL import Image,ImageOps
from tg.msg import MsgProxy
from tg.colors import get_color,cyan,bold
from media import clean_text,dimensions,ROOT
from native_image import draw as draw_image
from sticker_gallery import PreviewPool

KINDS={'messagePhoto':'Фото','messageSticker':'Стикер','messageAnimation':'GIF'}

def file_for(message):
    content=message['content'];kind=content.get('@type')
    if kind=='messagePhoto':
        sizes=content.get('photo',{}).get('sizes',[])
        if not sizes:raise ValueError('В сообщении нет фотографии')
        return max(sizes,key=lambda s:s.get('width',0)*s.get('height',0) or s.get('photo',{}).get('size',0)).get('photo',{})
    field='sticker' if kind=='messageSticker' else 'animation'
    return content.get(field,{}).get(field,{})

def metadata(controller,message):
    proxy=MsgProxy(message);model=controller.model
    chat=next((c for c in model.chats.chats if c.get('id')==message['chat_id']),{})
    sender_id=proxy.sender_id or message['chat_id']
    user=getattr(model.users,'users',{}).get(sender_id,{})
    name=' '.join(str(user.get(k,'')) for k in ('first_name','last_name')).strip()
    if not name:
        sender=next((c for c in model.chats.chats if c.get('id')==sender_id),{})
        name=sender.get('title','')
    edited=message.get('edit_date',0)
    date=proxy.date.strftime('%d.%m.%Y · %H:%M:%S')
    if edited:date+=' · изменено '+datetime.fromtimestamp(edited).strftime('%d.%m.%Y %H:%M')
    if message.get('forward_info'):date+=' · переслано'
    return {'kind':KINDS.get(message['content']['@type'],'Медиа'),'sender':clean_text(name) or 'Отправитель загружается…','sender_id':sender_id,'chat':clean_text(chat.get('title','Переписка')),'date':date,'caption':clean_text(proxy.caption or ''),'timestamp':proxy.date.strftime('%Y%m%d_%H%M%S')}


def prepare(controller,message,info):
    from features import request
    file=file_for(message);source=file.get('local',{}).get('path')
    local=file.get('local',{})
    if not source or not Path(source).is_file() or local.get('is_downloading_completed') is False:
        if not file.get('id'):raise ValueError('Файл недоступен')
        data=request(controller.tg,{'@type':'downloadFile','file_id':file['id'],'priority':32,'synchronous':True})
        source=data.get('local',{}).get('path')
    if not source or not Path(source).is_file():raise ValueError('Файл ещё не загрузился')
    display=source
    cache=Path.home()/'.cache/ttelegram/viewer';cache.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(f'{source}:{Path(source).stat().st_mtime_ns}'.encode()).hexdigest()
    if Path(source).suffix.lower()=='.tgs':
        display=str(cache/(key+'.gif'))
        if not Path(display).exists():subprocess.run([sys.executable,str(ROOT/'tgs_render.py'),source,display],capture_output=True,timeout=45,check=True)
    else:
        try:
            with Image.open(source) as image:image.verify()
        except OSError:
            display=str(cache/(key+'.webp'))
            if not Path(display).exists():
                subprocess.run(['ffmpeg','-v','error','-y','-i',source,'-vf','fps=8,scale=min(960\\,iw):-2','-c:v','libwebp_anim','-q:v','82','-loop','0',display],capture_output=True,timeout=45,check=True)
    if info['sender']=='Отправитель загружается…':
        try:
            data=request(controller.tg,{'@type':'getUser' if info['sender_id']>0 else 'getChat','user_id' if info['sender_id']>0 else 'chat_id':info['sender_id']})
            name=data.get('title') or ' '.join(str(data.get(k,'')) for k in ('first_name','last_name')).strip()
        except (RuntimeError,TimeoutError):name=''
    else:name=info['sender']
    with Image.open(display) as image:
        width,height=ImageOps.exif_transpose(image).size
    return {'source':source,'display':display,'sender':name or 'Пользователь','width':width,'height':height,'size':Path(source).stat().st_size}


class Viewer:
    def __init__(self,controller,message):
        self.controller=controller;self.pool=PreviewPool(workers=2);self.buttons=[];self.caption_scroll=0
        self.items=[]
        model=controller.model
        for mid in model.msgs.msg_ids[message['chat_id']]:
            msg=model.msgs.msgs[message['chat_id']].get(mid)
            if msg and msg.get('content',{}).get('@type') in KINDS:self.items.append(msg)
        if not any(m['id']==message['id'] for m in self.items):self.items.insert(0,message)
        self.position=next(i for i,m in enumerate(self.items) if m['id']==message['id'])
        self.load(message)
    def load(self,message):
        if getattr(self,'image',None):self.image.close()
        if getattr(self,'future',None):self.future.cancel()
        self.message=message;self.info=metadata(self.controller,message);self.asset=None;self.error='';self.status='';self.caption_scroll=0
        self.frame=0;self.frame_due=0;self.image=None;self.last_frame=None
        self.future=self.pool.submit(prepare,self.controller,dict(message),dict(self.info))
    def move(self,delta):
        index=max(0,min(len(self.items)-1,self.position+delta))
        if index!=self.position:
            self.position=index;self.load(self.items[index])
            ids=self.controller.model.msgs.msg_ids[self.message['chat_id']]
            if self.message['id'] in ids:self.controller.model.msgs.current_msgs[self.message['chat_id']]=ids.index(self.message['id'])
    def poll(self):
        if self.future and self.future.done():
            try:
                self.asset=self.future.result();self.info['sender']=self.asset['sender']
                self.image=Image.open(self.asset['display']);self.total=getattr(self.image,'n_frames',1)
                self.frame_due=time.monotonic();self.future=None
            except Exception:
                self.error='Не удалось загрузить медиа. R — повторить, Esc — назад.';self.future=None
        if self.image and self.total>1 and time.monotonic()>=self.frame_due:
            self.image.seek(self.frame);self.image.load()
            delay=max(.08,self.image.info.get('duration',100)/1000)
            self.frame_due=time.monotonic()+delay
            self.frame=(self.frame+1)%self.total
    def frame_path(self):
        if self.total==1:return self.asset['display']
        # Keep decoded animation frames cached; the original file stays intact.
        key=hashlib.sha256(f"{self.asset['display']}:{Path(self.asset['display']).stat().st_mtime_ns}".encode()).hexdigest()
        folder=Path.home()/'.cache/ttelegram/viewer-frames';folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'{key}-{self.image.tell()}.png'
        if not path.exists():self.image.convert('RGBA').save(path)
        return str(path)
    @synchronized
    def draw(self,screen):
        self.poll();h,w=screen.getmaxyx()
        frame_id=self.image.tell() if self.image else -1
        signature=(h,w,frame_id,self.position,self.asset is not None,self.error,self.caption_scroll,self.status)
        if signature==self.last_frame:return
        self.last_frame=signature;begin_frame(screen);screen.erase();self.buttons=[]
        accent=get_color(cyan,-1)|bold
        def put(y,x,text,attr=0):
            if 0<=y<h and 0<=x<w-1:
                try:screen.addstr(y,x,str(text)[:w-x-1],attr)
                except curses.error:pass
        heading=f"{self.info['kind']} · {self.position+1}/{len(self.items)}"
        if self.asset:heading+=f" · {self.asset['width']}×{self.asset['height']}"
        put(0,2,heading,accent)
        close='[Закрыть ×]';cx=max(2,w-len(close)-2);put(0,cx,close,accent);self.buttons.append((0,cx,w-1,'close'))
        put(1,2,'Отправитель: '+self.info['sender'],accent)
        put(2,2,self.info['date']+' · '+self.info['chat'])
        captions=[]
        for paragraph in self.info['caption'].split('\n'):captions.extend(textwrap.wrap(paragraph,max(10,w-6)) or [''])
        if not self.info['caption']:captions=['Без подписи']
        visible=min(max(1,h//5),len(captions),8)
        self.caption_scroll=min(self.caption_scroll,max(0,len(captions)-visible))
        caption_top=max(5,h-visible-5);put(caption_top,2,'Подпись',accent)
        for index,line in enumerate(captions[self.caption_scroll:self.caption_scroll+visible]):put(caption_top+1+index,2,line)
        x=2
        for title,action in [('← Предыдущее','previous'),('Следующее →','next'),('Оригинал O','original'),('Сохранить S','save'),('Закрыть Esc','close')]:
            label='['+title+'] '
            if x+len(label)>=w:break
            put(h-3,x,label,accent);self.buttons.append((h-3,x,x+len(label)-1,action));x+=len(label)
        put(h-2,2,self.status or 'Esc — назад · ←/→ — соседние медиа · PgUp/PgDn — подпись · Ctrl+Q — выйти')
        screen.refresh()
        if self.asset:
            try:
                path=self.frame_path();cols,rows=dimensions(path,max(2,w-4),max(2,caption_top-5))
                draw_image(screen,path,4,max(1,(w-cols)//2),cols,rows)
            except (OSError,ValueError,subprocess.SubprocessError):put(5,2,'Не удалось показать изображение. O — открыть оригинал.')
        else:
            put(max(5,caption_top//2),3,self.error or 'Загружаю оригинал… Esc — вернуться без ожидания.')
            screen.refresh()
    def action(self,name):
        if name=='close':return True
        if name=='previous':self.move(1)
        elif name=='next':self.move(-1)
        elif name=='retry':self.load(self.message)
        elif name=='original' and self.asset:subprocess.Popen(['xdg-open',self.asset['source']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif name=='save' and self.asset:
            suffix=Path(self.asset['source']).suffix or '.png'
            target=Path.home()/'Downloads'/('Telegram_'+self.info['timestamp']+suffix)
            result=subprocess.run(['kdialog','--title','Сохранить оригинал','--getsavefilename',str(target)],capture_output=True,text=True)
            if result.returncode==0 and result.stdout.strip():
                dest=Path(result.stdout.strip())
                if dest.resolve()!=Path(self.asset['source']).resolve():shutil.copy2(self.asset['source'],dest)
                self.status='Оригинал сохранён.'
        return False
    def run(self,screen):
        curses.curs_set(0);curses.mousemask(curses.ALL_MOUSE_EVENTS);screen.keypad(True);screen.timeout(80)
        try:
            while True:
                self.draw(screen)
                try:key=screen.get_wch()
                except curses.error:continue
                if key in ('\x11','\x0c'):
                    self.controller.view.status.pending_action='quit' if key=='\x11' else 'chat_list';return
                if key in ('\x0f',curses.KEY_F4):
                    self.controller.view.status.pending_action='settings';return
                if key in ('\x1b','q','\n'):return
                if key==curses.KEY_LEFT:self.move(1)
                elif key==curses.KEY_RIGHT:self.move(-1)
                elif key in ('r','R'):self.action('retry')
                elif key in ('o','O'):self.action('original')
                elif key in ('s','S'):self.action('save')
                elif key==curses.KEY_NPAGE:self.caption_scroll+=3
                elif key==curses.KEY_PPAGE:self.caption_scroll=max(0,self.caption_scroll-3)
                elif key==curses.KEY_MOUSE:
                    try:_,x,y,_,buttons=curses.getmouse()
                    except curses.error:continue
                    if buttons & getattr(curses,'BUTTON4_PRESSED',0):self.caption_scroll=max(0,self.caption_scroll-1)
                    elif buttons & getattr(curses,'BUTTON5_PRESSED',0):self.caption_scroll+=1
                    elif buttons&(curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED):
                        name=next((name for row,left,right,name in self.buttons if row==y and left<=x<right),None)
                        if name and self.action(name):return
        finally:
            if self.image:self.image.close()
            self.pool.shutdown(wait=False,cancel_futures=True)

def show(controller):
    from overlay import open_overlay,run_modal
    message=controller.model.current_msg
    with open_overlay(controller,'Просмотр медиа · Esc — назад',zoom=True):
        run_modal(controller,Viewer(controller,message).run)
