"""One event loop, explicit windows; keys never change pane geometry implicitly."""
import curses,logging,time,sys
from tg.views import Win
from tg.colors import get_color,cyan,bold
from native_image import clear,synchronized
import session_state
log=logging.getLogger(__name__)

class Engine:
    def __init__(self,controller):
        self.c=controller;self.s=controller.view.status;self.c.engine=self;self.s.engine=self
        self.query='';self.list_index=0;self.list_offset=0;self.focus='input';self.auto_restore=True;self.voices={}
        self.c.view_mode='chats';self.s.controller=controller;self.s.active=False;self.s.draft_key=None
    @property
    def voice(self):return self.voices.get(self.s.draft_key)
    def freeze_voice(self):
        if self.voice and self.voice.state=='recording':self.voice.stop()
        self.sync_voice()
    def sync_voice(self):
        if self.voice:
            item=self.voice.draft()
            if item:
                items=self.s.attachments.setdefault(self.s.draft_key,[])
                if not any(x.get('path')==item['path'] for x in items):items.append(item)
    def toggle_voice(self):
        if not self.c.can_send_msg():return
        voice=self.voice
        if voice and voice.state=='recording':voice.stop();self.sync_voice()
        elif not voice or voice.state=='error':
            if voice:voice.close()
            from voice_inline import InlineVoice
            voice=InlineVoice(self.c);self.voices[self.s.draft_key]=voice;voice.start()
        else:self.cancel_voice();self.toggle_voice()
    def cancel_voice(self):
        voice=self.voices.pop(self.s.draft_key,None)
        if voice:
            self.s.attachments[self.s.draft_key]=[x for x in self.s.attachments.get(self.s.draft_key,[]) if x.get('path')!=str(voice.path)]
            voice.keep=False;voice.close()
    def save_draft(self):
        self.sync_voice()
        if self.s.draft_key:self.s.drafts[self.s.draft_key]=self.s.buffer
        session_state.save(self.c)
    def chats(self):
        items=self.c.model.chats.chats
        return [chat for chat in items if self.query.casefold() in chat.get('title','').casefold()]
    def select_chat(self,step):
        self.list_index=max(0,min(len(self.chats())-1,self.list_index+step));self.c.render_chats()
    def open_list(self):
        self.freeze_voice();self.save_draft();self.auto_restore=False
        self.c.restore_ready=None;self.c.restore_chat_id=None
        from workspace_mode import set_mode
        set_mode('Чаты · Enter — открыть · Ctrl+O — настройки')
        self.c.view_mode='chats';self.s.active=False;self.s.draft_key=None;self.s.buffer='';self.s.pos=0;self.query=''
        items=self.chats();wanted=self.c.last_open_chat_id
        self.list_index=next((i for i,chat in enumerate(items) if chat['id']==wanted),0)
        self.c.resize()
    def open_chat(self,chat_id=None):
        self.freeze_voice();self.save_draft()
        items=self.chats()
        if chat_id is None:
            if not items:return
            chat_id=items[min(self.list_index,len(items)-1)]['id']
        if not self.c.model.set_current_chat_by_id(chat_id):return
        from workspace_mode import set_mode
        set_mode('Переписка · Ctrl+L — чаты · Ctrl+G — голосовое')
        self.c.view_mode='messages';self.focus='input';self.s.active=True;self.s.draft_key=f'chat:{chat_id}'
        self.s.buffer=self.s.drafts.get(self.s.draft_key,'');self.s.pos=len(self.s.buffer)
        if not self.voice:
            item=next((x for x in self.s.attachments.get(self.s.draft_key,[]) if x.get('kind')=='voice'),None)
            if item:
                from voice_inline import InlineVoice
                self.voices[self.s.draft_key]=InlineVoice.restore(self.c,item)
        from recovery import remember
        remember(self.c);self.c.resize()
    def process_pending(self):
        key=self.s.pending_action;self.s.pending_action=None
        if key=='quit':
            from recovery import quit_client
            quit_client(self.c)
        elif key=='chat_list':self.open_list()
        elif key:self.action(key)
    def action(self,key):
        self.save_draft()
        if key=='chats':self.open_list();return
        if key=='voice' and self.c.view_mode=='messages':self.toggle_voice();self.s.paint();return
        if key=='voice_play':
            if self.voice and self.voice.state=='review':self.voice.play()
            return
        if key=='voice_cancel':self.cancel_voice();return
        if key=='settings':
            self.freeze_voice()
            from settings import show
            show(self.c)
        elif key=='help':
            from context_help import show
            show(self.c)
        elif self.c.view_mode!='messages':
            self.s.notice='Сначала откройте чат: Enter или клик по строке.'
        elif key=='compose':self.focus='input';self.s.active=True
        elif key=='send':self.send()
        elif key=='paste':self.s.paste()
        elif key=='open':
            from tg.controllers import msg_handler
            msg_handler['l'](self.c,1)
        elif key in ('document','photo','gif','voice','stickers','gif_gallery','forward'):
            from mouse_ui import action
            action(self.c,key)
        elif key=='reply':self.reply()
        self.process_pending()
        self.s.paint()
    def reply(self):
        if not self.c.model.current_msg:return
        chat_id=self.c.model.current_chat_id;message_id=self.c.model.current_msg_id
        previous=(self.s.buffer,self.s.pos,self.s.active,self.s.draft_key,self.s.caption)
        self.s.draft_key=None
        try:
            text=self.s.get_input('Ответ на выбранное сообщение: ')
            if text:self.c.tg.reply_message(chat_id,message_id,text).wait(timeout=20,raise_exc=True)
        finally:self.s.buffer,self.s.pos,self.s.active,self.s.draft_key,self.s.caption=previous
    def send(self):
        if self.c.view_mode!='messages' or not self.c.can_send_msg():return
        if self.voice:
            self.freeze_voice();voice=self.voice
            if voice.state!='review':self.s.notice=voice.error;return
            self.c.tg.send_voice(str(voice.path),self.c.model.current_chat_id,voice.duration,voice.waveform).wait(timeout=30,raise_exc=True)
            self.s.attachments[self.s.draft_key]=[x for x in self.s.attachments.get(self.s.draft_key,[]) if x.get('path')!=str(voice.path)]
            voice.keep=True;voice.close();self.voices.pop(self.s.draft_key,None);self.s.notice='Голосовое передано Telegram';self.save_draft();return
        from media import send_attachments
        from attachments import consume_drop_suffix
        consume_drop_suffix(self.s)
        items=self.s.attachments.get(self.s.draft_key,[])
        if items:send_attachments(self.c,items,self.s.buffer)
        elif self.s.buffer.strip():
            if self.c.model.send_message(text=self.s.buffer) is False:return
        else:return
        self.s.buffer='';self.s.pos=0;self.s.drafts.pop(self.s.draft_key,None);session_state.save(self.c)
    def mouse(self):
        try:_,x,y,_,buttons=curses.getmouse()
        except curses.error:return
        if buttons&(getattr(curses,'BUTTON4_PRESSED',0)|getattr(curses,'BUTTON5_PRESSED',0)):
            up=bool(buttons&getattr(curses,'BUTTON4_PRESSED',0))
            if self.c.view_mode=='chats':self.select_chat(-3 if up else 3)
            elif up:self.c.prev_msg(3)
            else:self.c.next_msg(3)
            return
        if not buttons&(curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED|curses.BUTTON1_DOUBLE_CLICKED):return
        if y>=self.s.y:
            for row,left,right,key in self.s.buttons:
                if y==self.s.y+row and left<=x<right:self.action(key);return
            if self.c.view_mode=='messages':self.focus='input';self.s.active=True
            return
        if self.c.view.chats.w and x<self.c.view.chats.w:
            visible=getattr(self.c.view.chats,'mouse_chats',[])
            if 1<=y<=len(visible):self.open_chat(visible[y-1]['id'])
            return
        if self.c.view_mode=='messages' and self.c.view.msgs.w:
            rows=[(row,index) for row,index in getattr(self.c.view.msgs,'_mouse_rows',[]) if row<=y]
            if rows:
                _,index=max(rows);cid=self.c.model.current_chat_id
                self.c.model.msgs.current_msgs[cid]=index;self.c.render_msgs()
                kind=self.c.model.current_msg.get('content',{}).get('@type')
                media_hit=any(top<=y<top+height and left<=x<left+width for top,left,height,width,*rest in getattr(self.c.view.msgs,'_media_hitboxes',[]))
                if kind in ('messagePhoto','messageSticker','messageAnimation') and media_hit:self.action('open')
                else:self.save_draft();self.focus='messages';self.s.active=False
    def key(self,key):
        c=self.c
        if key=='\x11':
            self.freeze_voice();self.save_draft()
            from recovery import quit_client
            quit_client(c);return
        if key=='\x0c':self.open_list();return
        if key in ('\x0f',curses.KEY_F4):self.action('settings');return
        if key==curses.KEY_F1:self.action('help');return
        if key=='\x12':
            from recovery import start_bootstrap
            start_bootstrap(c);return
        if key==curses.KEY_MOUSE:self.mouse();return
        if key==curses.KEY_RESIZE:c.resize();return
        if c.view_mode=='chats':
            if key in (curses.KEY_UP,curses.KEY_DOWN):self.select_chat(-1 if key==curses.KEY_UP else 1)
            elif key in ('\n','\r',curses.KEY_ENTER):self.open_chat()
            elif key=='\x1b':self.query='';self.s.buffer='';self.s.pos=0;self.s.active=False;c.render_chats()
            elif key in ('\x7f','\b',curses.KEY_BACKSPACE):self.query=self.query[:-1];self.s.buffer=self.query;self.s.pos=len(self.query);self.list_index=0;c.render_chats()
            elif key=='\x06':self.s.active=True
            elif isinstance(key,str) and key.isprintable():
                self.query+=key;self.s.buffer=self.query;self.s.pos=len(self.query);self.s.active=True;self.list_index=0;c.render_chats()
            return
        if self.voice and key in ('p','P'):
            if self.voice.state=='review':self.voice.play()
            return
        if self.voice and key in ('\x1b','\x04'):self.cancel_voice();return
        if self.voice and key in ('\n','\r',curses.KEY_ENTER):self.send();return
        if self.voice and isinstance(key,str) and key.isprintable():return
        if key=='\x1b':self.open_list();return
        if key=='\x15':self.action('document');return
        if key in ('\x07',):self.action('voice');return
        if key in ('\x14',curses.KEY_F7):self.action('stickers');return
        if key=='\t':
            self.save_draft();self.focus='messages' if self.focus=='input' else 'input';self.s.active=self.focus=='input';return
        if key in (curses.KEY_PPAGE,curses.KEY_NPAGE,curses.KEY_UP,curses.KEY_DOWN):
            amount=10 if key in (curses.KEY_PPAGE,curses.KEY_NPAGE) else 1
            if key in (curses.KEY_UP,curses.KEY_PPAGE):c.prev_msg(amount)
            else:c.next_msg(amount)
            return
        if self.focus=='messages':
            if key in ('\n',curses.KEY_ENTER):self.action('open')
            elif key==' ':c._toggle_select_msg();c.render_msgs()
            return
        if key in ('\n','\r',curses.KEY_ENTER):self.send()
        elif key=='\x16':self.action('paste')
        elif key=='\x04':
            from media import forget_attachment
            items=self.s.attachments.get(self.s.draft_key,[])
            if items:forget_attachment(items.pop())
        elif key=='\x01':self.s.pos=0
        elif key=='\x05':self.s.pos=len(self.s.buffer)
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_HOME,curses.KEY_END,curses.KEY_DC,curses.KEY_BACKSPACE,'\x7f','\b'):
            if key in ('\x7f','\b'):key=curses.KEY_BACKSPACE
            self.s.buffer,self.s.pos=self.s._edit_key(key,self.s.buffer,self.s.pos)
        elif isinstance(key,str) and key.isprintable():
            self.s.buffer=self.s.buffer[:self.s.pos]+key+self.s.buffer[self.s.pos:];self.s.pos+=len(key)
    def run(self):
        from recovery import start_bootstrap,quit_client
        sys.stdout.write("\033[?2004h");sys.stdout.flush()
        curses.set_escdelay(25)
        start_bootstrap(self.c);self.c.resize()
        try:
            while self.c.is_running:
                if self.c.restore_ready is not None:
                    wanted=self.c.restore_ready;self.c.restore_ready=None
                    if self.auto_restore:self.open_chat(wanted)
                try:
                    self.s.paint();win=self.s.win;win.timeout(150)
                    if self.s.active and not self.voice:curses.curs_set(1);key=win.get_wch(1,min(getattr(self.s,'cursor',4),self.s.w-2))
                    else:curses.curs_set(0);key=win.get_wch()
                except curses.error:
                    if self.c.view_mode=='messages' and self.s.active:
                        from attachments import consume_drop_suffix
                        consume_drop_suffix(self.s)
                    time.sleep(.02)
                    session_state.save(self.c,force=False);continue
                if key=='\x1b':
                    win.timeout(25);sequence=''
                    try:
                        while len(sequence)<5:
                            char=win.get_wch()
                            if isinstance(char,str):sequence+=char
                            if sequence.endswith('~'):break
                    except curses.error:pass
                    if sequence=='[200~':
                        pasted='';win.timeout(1000)
                        try:
                            while len(pasted)<1_000_000:
                                char=win.get_wch()
                                if isinstance(char,str):pasted+=char
                                if pasted.endswith('\x1b[201~'):pasted=pasted[:-6];break
                        except curses.error:pass
                        if self.c.view_mode=='messages':
                            from attachments import attach_text
                            if not attach_text(self.s,pasted):
                                self.s.buffer=self.s.buffer[:self.s.pos]+pasted+self.s.buffer[self.s.pos:];self.s.pos+=len(pasted)
                        else:
                            self.query+=pasted.replace('\n',' ');self.s.buffer=self.query;self.s.pos=len(self.query);self.c.render_chats()
                        continue
                self.auto_restore=False
                try:self.key(key);self.process_pending();self.s.paint();session_state.save(self.c,force=False)
                except Exception:log.exception('UI action failed');self.s.notice='Не удалось выполнить действие. Ctrl+L — чаты, Ctrl+Q — выход.';self.c.resize()
        finally:
            self.freeze_voice();self.save_draft()
            for voice in self.voices.values():voice.close()
            self.c.queue.put(lambda:quit_client(self.c))

def install():
    from tg import controllers
    from ui import state
    old_render_msgs=controllers.Controller._render_msgs
    def run(self):Engine(self).run()
    controllers.Controller.run=run
    @synchronized
    def resize(self):
        if getattr(self,'gallery_active',False):return
        rows,cols=self.view.stdscr.getmaxyx();reserved=min(5,max(1,rows-3));h=rows-reserved
        clear(self.view.stdscr)
        sidebar=self.view_mode=='messages' and state().get('layout')=='sidebar'
        chat_width=cols if self.view_mode=='chats' else (max(16,cols//4) if sidebar else 0)
        for view,width,x in ((self.view.chats,chat_width,0),(self.view.msgs,cols-chat_width,chat_width)):
            view.h=h;view.w=width;view.x=x
            if width:
                view.win=Win(curses.newwin(h,width,0,x));view.win.keypad(True);view._refresh=view.win.refresh
        self.chat_size=chat_width/max(1,cols);self.view.status.resize(rows,cols);self._render()
    controllers.Controller._resize=resize
    def render_chats(self):
        if getattr(self,'gallery_active',False) or not self.view.chats.w:return
        engine=getattr(self,'engine',None)
        if engine is None:return
        items=engine.chats() if self.view_mode=='chats' else self.model.chats.chats
        selected=engine.list_index if self.view_mode=='chats' else self.model.current_chat
        size=max(1,self.view.chats.h-1)
        engine.list_offset=min(max(0,selected-size+1),engine.list_offset) if selected<engine.list_offset else max(engine.list_offset,selected-size+1)
        start=max(0,min(engine.list_offset,max(0,len(items)-size)));engine.list_offset=start
        self.view.chats.draw(max(0,selected-start),items[start:start+size],'Чаты · '+str(len(items)))
    controllers.Controller._render_chats=render_chats
    def render_msgs(self):
        if self.view_mode=='messages' and self.view.msgs.w:old_render_msgs(self)
    controllers.Controller._render_msgs=render_msgs
    @synchronized
    def render(self):
        if getattr(self,'gallery_active',False):return
        self.view.status.paint();self._render_chats();self._render_msgs()
    controllers.Controller._render=render
