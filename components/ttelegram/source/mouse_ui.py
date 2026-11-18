"""Mouse routing and visible action buttons."""
import curses
import subprocess
from pathlib import Path


def file_picker(kind='photo'):
    title='Выбрать GIF' if kind=='gif' else 'Прикрепить изображение'
    filters='Анимация (*.gif *.mp4 *.webm)' if kind=='gif' else 'Изображения (*.png *.jpg *.jpeg *.webp *.gif)'
    if kind=='document':title='Прикрепить файл';filters='Все файлы (*)'
    result=subprocess.run(['kdialog','--title','ttelegram / '+title,'--getopenfilename',str(Path.home()/'Pictures'),filters],capture_output=True,text=True)
    if result.returncode or not result.stdout.strip(): return None
    from PIL import Image
    path=Path(result.stdout.strip())
    if kind=='document':
        from attachments import item_for
        return item_for(path)
    item={'kind':'image','path':str(path),'owned':False}
    if kind=='gif': item['kind']='animation'
    try:
        with Image.open(path) as im: item.update(width=im.width,height=im.height)
    except OSError:
        if kind!='gif': raise
    return item


def action(controller,key):
    status=controller.view.status
    from tg.controllers import msg_handler
    draft_key=f'chat:{controller.model.current_chat_id}'
    if key=='gif_gallery':
        from features import stickers
        stickers(controller,'gifs')
    elif key in ('photo','gif','document'):
        item=file_picker(key)
        if item: status.attachments.setdefault(draft_key,[]).append(item)
    elif key=='settings':
        from settings import show
        show(controller); controller.render()
    elif key=='chats':
        status.pending_action='chat_list'
    elif key in ('voice','stickers','forward','reply'):
        msg_handler[{'voice':'v','stickers':'t','forward':'f','reply':'r'}[key]](controller,1)


def event(controller,editing=False):
    try: _,x,y,_,buttons=curses.getmouse()
    except curses.error: return None
    status=controller.view.status
    if buttons & getattr(curses,'BUTTON4_PRESSED',0):
        controller.prev_msg(3); return None
    if buttons & getattr(curses,'BUTTON5_PRESSED',0):
        controller.next_msg(3); return None
    click=buttons & (curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED|curses.BUTTON1_DOUBLE_CLICKED)
    if not click: return None
    if y>=status.y:
        for button in getattr(status,'buttons',[]):
            row,start,end,key=button if len(button)==4 else (2,*button)
            if y==status.y+row and start<=x<end:return key
        return 'compose'
    if x<controller.view.chats.w and controller.view.chats.w:
        rendered=getattr(controller.view.chats,'mouse_chats',[])
        if 1<=y<=len(rendered):
            controller.model.set_current_chat_by_id(rendered[y-1]['id'])
            # Upstream set_current_chat erroneously rejects chat index zero.
            if rendered[y-1]['id']==controller.model.chats.chats[0]['id']: controller.model.current_chat=0
            controller.render();return 'chat_changed'
    if y<controller.view.msgs.h:
        candidates=[(row,index) for row,index in getattr(controller.view.msgs,'_mouse_rows',[]) if row<=y]
        if candidates:
            _,index=max(candidates)
            chat_id=controller.model.current_chat_id
            if chat_id is not None:
                controller.model.msgs.current_msgs[chat_id]=index
                controller.render_msgs()
                msg=controller.model.current_msg
                media=msg.get('content',{}).get('@type') in ('messagePhoto','messageSticker','messageAnimation')
                if media:return 'open'
                if editing:return 'open' if buttons & curses.BUTTON1_DOUBLE_CLICKED else 'history'
    if buttons & curses.BUTTON1_DOUBLE_CLICKED:
        return 'open'
    return None


def install():
    from tg import views,controllers
    views.SPECIAL_KEYS[curses.KEY_MOUSE]='_MOUSE'
    views.SPECIAL_KEYS[curses.KEY_F4]='_SETTINGS'
    views.SPECIAL_KEYS[curses.KEY_F7]='_STICKERS'
    original_init=views.View.__init__
    def init(self,*args,**kwargs):
        original_init(self,*args,**kwargs)
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        curses.mouseinterval(180)
    views.View.__init__=init
    original_chat_draw=views.ChatView.draw
    def chat_draw(self,current,chats,title='Chats'):
        if getattr(self,'gallery_active',False):return
        self.mouse_chats=chats
        return original_chat_draw(self,current,chats,title)
    views.ChatView.draw=chat_draw
    controllers.msg_handler['_SETTINGS']=lambda self,repeat=1:action(self,'settings')
    controllers.chat_handler['_SETTINGS']=controllers.msg_handler['_SETTINGS']
    controllers.msg_handler['^O']=controllers.msg_handler['_SETTINGS']
    controllers.chat_handler['^O']=controllers.msg_handler['_SETTINGS']
    controllers.msg_handler['^G']=lambda self,repeat=1:action(self,'voice')
    controllers.chat_handler['^G']=controllers.msg_handler['^G']
    controllers.msg_handler['_STICKERS']=lambda self,repeat=1:action(self,'stickers')
    controllers.chat_handler['_STICKERS']=controllers.msg_handler['_STICKERS']
    def click(self,repeat=1):
        key=event(self)
        if key=='chat_changed':
            return controllers.chat_handler['^J'](self,1)
        if key in ('compose','send','paste'):
            from composer import compose
            if key=='send':self.view.status.submit_requested=True
            if key=='paste':
                status=self.view.status;status.draft_key=f'chat:{self.model.current_chat_id}'
                status.buffer=status.drafts.get(status.draft_key,'');status.pos=len(status.buffer)
                status.paste();status.drafts[status.draft_key]=status.buffer
            compose(self)
        elif key=='open': controllers.msg_handler['l'](self,1)
        elif key:
            action(self,key)
            if key in ('photo','gif','gif_gallery','voice','stickers','forward','reply'):
                from composer import compose
                compose(self)
    controllers.msg_handler['_MOUSE']=click
    controllers.chat_handler['_MOUSE']=click
