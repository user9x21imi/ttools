"""Visible input panel and compose-first chat mode for ttelegram."""
import curses
import time
import sys
from pathlib import Path
from media import clipboard,clean_text,forget_attachment,send_attachments
from tg.views import StatusView, Win
from workspace_mode import set_mode
from tg.colors import get_color, cyan, bold
from native_image import synchronized
from tg.utils import string_len_dwc, truncate_to_len


class ComposerStatus(StatusView):
    def __init__(self, stdscr):
        self.stdscr=stdscr
        self.active=False; self.caption='Написать сообщение'; self.buffer=''; self.pos=0
        self.notice=''; self.draft_key=None; self.drafts={}; self.attachments={}; self.pending_action=None; self.controller=None; self.buttons=[]; self.submit_requested=False
        rows,cols=stdscr.getmaxyx()
        self.h=min(5,max(1,rows-3)); self.w=cols-1; self.y=rows-self.h; self.x=0
        self.win=Win(curses.newwin(self.h,self.w,self.y,0))
        self.win.keypad(True); self._refresh=self.win.refresh
        from session_state import restore_drafts
        restore_drafts(self)

    def resize(self, rows, cols):
        self.h=min(5,max(1,rows-3)); self.w=max(2,cols-1); self.y=rows-self.h
        self.win=Win(curses.newwin(self.h,self.w,self.y,0))
        self.win.keypad(True); self._refresh=self.win.refresh
        self.paint()

    @synchronized
    def paint(self):
        if getattr(self,'gallery_active',False):return
        self.win.erase()
        accent=get_color(cyan,-1)|bold
        is_list=getattr(self.controller,'view_mode','')=='chats'
        title=(self.caption+' · Ctrl+L — чаты · Ctrl+Q — выход') if self.active else ('Чаты · Enter — открыть · Ctrl+Q — выход' if getattr(self.controller,'view_mode','')=='chats' else 'Переписка · i/клик — ввод · Ctrl+L — чаты · Ctrl+Q — выход')
        if hasattr(self,'engine'):
            title='ЧАТЫ · ↑↓ выбор · Enter / клик — открыть' if is_list else ('ВВОД СООБЩЕНИЯ' if self.active else 'ВЫБОР СООБЩЕНИЯ · Tab — писать')
        heading='+-- '+title+' '
        self.win.addstr(0,0,truncate_to_len(heading+'-'*self.w,self.w-1),accent)
        if self.h>=2:
            avail=max(1,self.w-5)
            start=self.pos
            while start>0 and string_len_dwc(self.buffer[start-1:self.pos].replace('\n','↵'))<avail: start-=1
            text=truncate_to_len(self.buffer[start:].replace('\n','↵'),avail)
            if not text and self.active: text=''
            elif not text: text='Название чата для поиска…' if is_list else 'Ваше сообщение…'
            self.win.addstr(1,0,'| > ',accent)
            self.win.addstr(1,4,text)
            self.cursor=min(self.w-2,4+string_len_dwc(self.buffer[start:self.pos].replace('\n','↵')))
        if self.h>=3:
            self.buttons=[]; x=0;row=2;last_toolbar=self.h-2
            controls=[('Настройки Ctrl+O','settings'),('Подсказки F1','help')] if is_list else [('Голос Ctrl+G','voice'),('Стикеры Ctrl+T','stickers'),('GIF','gif_gallery'),('Вставить Ctrl+V','paste'),('Отправить Enter','send'),('Чаты Ctrl+L','chats'),('Файл Ctrl+U','document'),('Ответ','reply'),('Пересл.','forward'),('Настройки','settings'),('Помощь F1','help')]
            for title,key in controls:
                label='['+title+'] '
                if x+len(label)>=self.w:row+=1;x=0
                if row>last_toolbar:break
                self.win.addstr(row,x,label,accent);self.buttons.append((row,x,x+len(label)-1,key));x+=len(label)
        if self.h>=4:
            attached=self.attachments.get(self.draft_key,[]) if self.draft_key else []
            label=(f'Вложено: {len(attached)} · '+', '.join(('Файл '+Path(item['path']).name if item.get('kind')=='document' else ('GIF' if item.get('kind')=='animation' else 'Фото')+' '+str(item.get('width','?'))+'×'+str(item.get('height','?'))) for item in attached)+' | Ctrl+D — убрать последнее') if attached else (self.notice or 'Ctrl+O — настройки · Ctrl+V — вставить · Enter — отправить · Esc — чаты')
            if is_list:label=self.notice or 'Печатайте для поиска · Ctrl+O — настройки · F1 — подсказки · Ctrl+Q — сохранить и выйти'
            self.win.addstr(self.h-1,0,truncate_to_len(label,self.w-1))
        voice=getattr(getattr(self,'engine',None),'voice',None)
        if voice:
            elapsed=int(time.monotonic()-voice.started) if voice.state=='recording' else voice.duration
            playing=voice.playing
            label='● ЗАПИСЬ С МИКРОФОНА' if voice.state=='recording' else ('▶ ПРОСЛУШИВАНИЕ' if playing else 'ГОЛОСОВОЕ ГОТОВО')
            self.win.erase();self.buttons=[]
            self.win.addstr(0,0,truncate_to_len(f'+-- {label} · {elapsed//60:02}:{elapsed%60:02} '+'-'*self.w,self.w-1),accent)
            if self.h>1:self.win.addstr(1,0,truncate_to_len('| '+voice.bars(self.w-4),self.w-1),accent)
            controls=[('Стоп Ctrl+G','voice'),('Отправить Enter','send'),('Удалить Esc','voice_cancel')] if voice.state=='recording' else [('Стоп P' if playing else 'Прослушать P','voice_play'),('Отправить Enter','send'),('Заново Ctrl+G','voice'),('Удалить Esc','voice_cancel')]
            x=0
            if self.h>2:
                for title,key in controls:
                    text='['+title+'] '
                    if x+len(text)>=self.w:break
                    self.win.addstr(2,x,text,accent);self.buttons.append((2,x,x+len(text)-1,key));x+=len(text)
            if self.h>3:self.win.addstr(self.h-1,0,truncate_to_len(voice.error or 'Ctrl+G — остановить · P — прослушать/остановить · Enter — отправить',self.w-1))
            self.cursor=2
        self._refresh()

    def draw(self,msg=''):
        if msg: self.notice=msg.replace('\n',' ')
        self.paint()

    def get_input(self,prefix=''):
        self.active=True
        self.caption=prefix.strip() or 'Написать сообщение'
        self.buffer=self.drafts.get(self.draft_key,'') if self.draft_key else ''
        self.pos=len(self.buffer)
        curses.curs_set(1)
        sys.stdout.write('\033[?2004h');sys.stdout.flush()
        try:
            while True:
                if self.pending_action in ('quit','chat_list','settings'):return None
                if self.controller:
                    from session_state import save
                    save(self.controller,force=False)
                self.paint()
                if self.submit_requested:
                    self.submit_requested=False;break
                try:
                    key=self.win.get_wch(min(1,self.h-1),getattr(self,'cursor',0))
                except curses.error:
                    # A resize can invalidate a pending read before the drawing
                    # thread has replaced the input window.
                    time.sleep(.02)
                    continue
                if isinstance(key,int):
                    if key==curses.KEY_F7:
                        self.open_gallery()
                        if self.pending_action in ('quit','chat_list','settings'):return None
                        continue
                    if key in (curses.KEY_UP,curses.KEY_DOWN):
                        if self.draft_key:self.drafts[self.draft_key]=self.buffer
                        self.pending_action='history_up' if key==curses.KEY_UP else 'history_down'
                        return None
                    if key==curses.KEY_MOUSE and self.controller:
                        from mouse_ui import event
                        action=event(self.controller,editing=True)
                        if action in ('stickers','gif_gallery'):
                            self.open_gallery('gifs' if action=='gif_gallery' else 'recent')
                            if self.pending_action in ('quit','chat_list','settings'):return None
                            continue
                        if action=='paste': self.paste();continue
                        if action=='send': break
                        if action=='compose': continue
                        if action:
                            if self.draft_key: self.drafts[self.draft_key]=self.buffer
                            self.pending_action=action;return None
                        continue
                    if key==curses.KEY_F4:
                        if self.draft_key:self.drafts[self.draft_key]=self.buffer
                        self.pending_action='settings';return None
                    if key==curses.KEY_ENTER: break
                    if key!=curses.KEY_RESIZE:
                        self.buffer,self.pos=self._edit_key(key,self.buffer,self.pos)
                    continue
                code=ord(key)
                if code==7:
                    self.open_voice()
                    if self.pending_action in ('quit','chat_list','settings'):return None
                    continue
                if code==15:
                    if self.draft_key:self.drafts[self.draft_key]=self.buffer
                    self.pending_action='settings';return None
                if code in (17,12):
                    if self.draft_key:self.drafts[self.draft_key]=self.buffer
                    self.pending_action='quit' if code==17 else 'chat_list'
                    if self.controller:
                        from session_state import save
                        save(self.controller)
                    return None
                if code in (10,13): break
                if code==20:
                    self.open_gallery()
                    if self.pending_action in ('quit','chat_list','settings'):return None
                    continue
                if code==22:
                    self.paste();continue
                if code==4 and self.draft_key:
                    items=self.attachments.get(self.draft_key,[])
                    if items: forget_attachment(items.pop())
                    continue
                if code==27:
                    self.win.timeout(40)
                    sequence=''
                    try:
                        while len(sequence)<5:
                            char=self.win.get_wch()
                            if isinstance(char,str):sequence+=char
                            if sequence.endswith('~'):break
                    except curses.error:pass
                    finally:self.win.timeout(-1)
                    if sequence=='[200~':
                        pasted='';self.win.timeout(1000)
                        try:
                            while len(pasted)<1_000_000:
                                char=self.win.get_wch()
                                if isinstance(char,str):pasted+=char
                                if pasted.endswith('\033[201~'):
                                    pasted=pasted[:-6];break
                        except curses.error:pass
                        finally:self.win.timeout(-1)
                        pasted=clean_text(pasted)
                        self.buffer=self.buffer[:self.pos]+pasted+self.buffer[self.pos:];self.pos+=len(pasted)
                        continue
                if code in (7,27):
                    if code==27:self.pending_action='chat_list'
                    if self.draft_key: self.drafts[self.draft_key]=self.buffer
                    return None
                if code in (127,8): self.buffer,self.pos=self._edit_key(curses.KEY_BACKSPACE,self.buffer,self.pos)
                elif code==1: self.pos=0
                elif code==5: self.pos=len(self.buffer)
                elif key.isprintable():
                    self.buffer=self.buffer[:self.pos]+key+self.buffer[self.pos:]; self.pos+=1
            text=self.buffer
            if self.draft_key: self.drafts.pop(self.draft_key,None)
            return text
        finally:
            self.active=False; self.buffer=''; self.pos=0
            sys.stdout.write('\033[?2004l');sys.stdout.flush()
            curses.curs_set(0); curses.cbreak(); curses.noecho(); self.paint()


    def open_gallery(self,kind='recent'):
        if not self.controller:return
        from features import stickers
        # Keep the live input buffer and cursor intact while the picker is open.
        if self.draft_key:self.drafts[self.draft_key]=self.buffer
        stickers(self.controller,kind)
        curses.curs_set(1)
        self.paint()

    def open_voice(self):
        if not self.controller:return
        if self.draft_key:self.drafts[self.draft_key]=self.buffer
        from features import record_voice
        record_voice(self.controller)
        curses.curs_set(1);self.paint()

    def paste(self):
        self.notice='Читаю буфер обмена…';self.paint()
        try:
            item=clipboard()
            if item['kind'] in ('image','document','files'):
                if not self.draft_key:
                    self.notice='Откройте поле сообщения для прикрепления фото.';return
                self.attachments.setdefault(self.draft_key,[]).extend(item['items'] if item['kind']=='files' else [item])
                self.notice='Изображение прикреплено. Enter отправит оригинал.'
            elif item['kind']=='text':
                text=clean_text(item['text'])
                from attachments import attach_text
                if attach_text(self,text):return
                self.buffer=self.buffer[:self.pos]+text+self.buffer[self.pos:];self.pos+=len(text)
                self.notice='Текст вставлен. Enter — отправить.'
            else:self.notice='В буфере нет текста или изображения.'
        except ValueError as error:self.notice=str(error)


def compose(controller):
    chat_id=controller.model.current_chat_id
    if chat_id is None or not controller.can_send_msg():
        controller.present_info('В этом чате отправка сообщений недоступна')
        return
    status=controller.view.status
    set_mode('Ввод сообщения · Enter — отправить / Esc — действия')
    status.controller=controller
    status.draft_key=f'chat:{chat_id}'
    try:
        while True:
            text=status.get_input()
            if text is None: return
            items=status.attachments.get(status.draft_key,[])
            if items:
                status.drafts[status.draft_key]=text
                send_attachments(controller,items,text)
                status.drafts.pop(status.draft_key,None)
                status.notice='Вложение передано Telegram. Оригинал сохранён.'
                continue
            if not text.strip(): continue
            status.drafts[status.draft_key]=text
            if controller.model.send_message(text=text) is False:
                controller.present_error('Не удалось отправить. Черновик сохранён: нажмите i.')
                return
            status.drafts.pop(status.draft_key,None)
    finally:
        status.draft_key=None
        set_mode('Переписка · i — ввод / r — ответ / v — голос')


def install():
    from tg import views, controllers
    views.StatusView=ComposerStatus
    def resize(self):
        if getattr(self,'gallery_active',False):return
        rows,cols=self.view.stdscr.getmaxyx()
        from native_image import clear
        clear(self.view.stdscr)
        self.view.stdscr.erase(); self.view.stdscr.noutrefresh()
        reserved=min(5,max(1,rows-3))
        content_rows=rows-reserved+1
        chat_width=round(cols*self.chat_size)
        self.view.chats.resize(content_rows,cols,chat_width)
        self.view.msgs.resize(content_rows,cols,cols-chat_width)
        self.view.status.resize(rows,cols)
        self._render()
    controllers.Controller._resize=resize
    def handle(self,handlers,size):
        in_messages=handlers is controllers.msg_handler
        self.view_mode='messages' if in_messages else 'chats'
        if in_messages:
            from recovery import remember
            remember(self)
        self.chat_size=size; self.resize()
        composing=handlers is controllers.msg_handler
        while True:
            try:
                self.view_mode='messages' if in_messages else 'chats'
                set_mode('Переписка · Ctrl+L — чаты / Ctrl+Q — выход' if in_messages else 'Чаты · Enter — открыть / Ctrl+Q — выход')
                if composing:
                    composing=False; compose(self)
                    pending=self.view.status.pending_action
                    self.view.status.pending_action=None
                    if pending=='quit':return 'QUIT'
                    if pending=='chat_list':return 'BACK'
                    if pending in ('history','history_up','history_down'):
                        if pending=='history_up':self.prev_msg(1)
                        elif pending=='history_down':self.next_msg(1)
                        pending=None
                    if pending:
                        from mouse_ui import action
                        if pending not in ('chat_changed','open'):action(self,pending)
                        elif pending=='open':controllers.msg_handler['l'](self,1)
                        composing=True;continue
                repeat,keys=self.view.get_keys()
                if keys=='_TICK':
                    wanted=getattr(self,'restore_ready',None)
                    if not in_messages and wanted is not None:
                        self.restore_ready=None;self.restore_chat_id=None
                        if self.model.set_current_chat_by_id(wanted):
                            result=controllers.chat_handler['^J'](self,1)
                            if result=='QUIT':return 'QUIT'
                            self.view_mode='chats';self.chat_size=size;self.resize()
                    continue
                if handlers is controllers.msg_handler and keys in ('i','a'):
                    composing=True; continue
                before=self.model.current_chat_id
                result=handlers.get(keys,lambda *_:None)(self,repeat)
                pending=self.view.status.pending_action
                if pending=='settings':
                    self.view.status.pending_action=None
                    from mouse_ui import action
                    action(self,'settings')
                    pending=self.view.status.pending_action
                if pending in ('quit','chat_list'):
                    self.view.status.pending_action=None
                    if pending=='quit':return 'QUIT'
                    if in_messages:return 'BACK'
                    self.resize();continue
                if result in ('QUIT','BACK'): return result
                if handlers is controllers.msg_handler and before!=self.model.current_chat_id:
                    composing=True
            except Exception:
                controllers.log.exception('Composer action failed')
                self.present_error('Не удалось выполнить действие. Нажмите i, чтобы вернуться к вводу.')
    controllers.Controller.handle=handle
    controllers.msg_handler['i']=lambda self,repeat=1: compose(self)
    controllers.msg_handler['a']=lambda self,repeat=1: compose(self)
