"""Reliable startup, nonblocking chat/history loading and persistent session lifecycle."""
import curses,logging,os,signal,sys,threading
from pathlib import Path
import session_state

CURRENT=None
log=logging.getLogger(__name__)


def rpc(result):
    result.wait(timeout=10,raise_exc=True)
    return result.update or {}


def remember(controller):
    chat=controller.model.current_chat_id
    if chat is not None:
        controller.last_open_chat_id=chat
        controller.restore_chat_id=None
        controller.restore_ready=None
        session_state.save(controller)


def quit_client(controller):
    session_state.save(controller)
    controller.is_running=False
    controller.queue.put(lambda:None)
    return 'QUIT'


def bootstrap(controller):
    try:
        controller.model.chats._load_next_chats()
        wanted=controller.restore_chat_id
        if wanted is not None:
            if not any(c['id']==wanted for c in controller.model.chats.chats):
                chat=rpc(controller.tg.get_chat(wanted))
                if chat.get('id'):
                    chat.setdefault('order','0')
                    controller.model.chats.chats.append(chat)
                    controller.model.chats.chat_ids.add(chat['id'])
            if any(c['id']==wanted for c in controller.model.chats.chats):controller.restore_ready=wanted
        controller.view.status.notice='Ctrl+L — чаты · Ctrl+Q — сохранить и выйти'
    except (RuntimeError,TimeoutError,OSError):
        controller.view.status.notice='Не удалось загрузить чаты. Ctrl+R — повторить · Ctrl+Q — выйти'
        log.exception('Could not load chat list')
    finally:
        controller.bootstrap_running=False
        controller.render()


def start_bootstrap(controller):
    if getattr(controller,'bootstrap_running',False):return
    controller.model.msgs._history_ended.clear()
    controller.model.msgs._history_retry.clear()
    controller.bootstrap_running=True
    threading.Thread(target=bootstrap,args=(controller,),daemon=True,name='telegram-chat-loader').start()


def install():
    global CURRENT
    from tg import controllers,models,views,__main__ as app
    old_init=controllers.Controller.__init__
    def init(self,*args,**kwargs):
        global CURRENT
        old_init(self,*args,**kwargs)
        saved=session_state.read()
        self.last_open_chat_id=saved.get('last_chat_id');self.restore_chat_id=self.last_open_chat_id;self.restore_ready=None
        self.view_mode='chats';self.bootstrap_running=False
        self.view.status.controller=self
        self.view.status.notice='Загружаю чаты… · Ctrl+L — список · Ctrl+Q — выйти'
        self.model.chats.title='Чаты'
        self.model.chats.on_loaded=self.render
        self.model.msgs.on_loaded=self.render_msgs
        self.model.msgs._msg_lock=threading.RLock()
        self.model.msgs._history_loading=set()
        self.model.msgs._history_lock=threading.Lock()
        self.model.msgs._history_ended=set()
        self.model.msgs._history_retry={}
        self.model.msgs._history_rounds={}
        CURRENT=self
    controllers.Controller.__init__=init
    def add_message(self,chat_id,message):
        if not hasattr(self,'_msg_lock'):self._msg_lock=threading.RLock()
        with self._msg_lock:
            ids=self.msg_ids[chat_id]
            current=self.current_msgs[chat_id]
            selected=ids[current] if 0<current<len(ids) else None
            self.msgs[chat_id][message['id']]=message
            self.msg_ids[chat_id]=sorted(set(ids)|{message['id']},reverse=True)
            if selected in self.msg_ids[chat_id]:self.current_msgs[chat_id]=self.msg_ids[chat_id].index(selected)
            else:self.current_msgs[chat_id]=min(current,max(0,len(self.msg_ids[chat_id])-1))
    models.MsgModel.add_message=add_message
    # Upstream rejected the first chat (index zero).
    def set_current(self,index):
        if 0<=index<len(self.chats.chats):self.current_chat=index;return True
        return False
    models.Model.set_current_chat=set_current
    def load_chats(self):
        try:rpc(self.tg.load_chats(limit=max(100,self.chats_limit)))
        except RuntimeError:pass  # 404 means the full list is already loaded.
        self.chats_limit=max(100,self.chats_limit)
        ids=rpc(self.tg.get_chats(limit=self.chats_limit)).get('chat_ids',[])
        for chat_id in ids:
            if chat_id not in self.chat_ids:
                chat=rpc(self.tg.get_chat(chat_id))
                if chat:self.add_chat(chat)
        self.have_full_chat_list=len(ids)<self.chats_limit
    models.ChatModel._load_next_chats=load_chats
    # Rendering must never wait on network requests.
    models.ChatModel.fetch_chats=lambda self,offset=0,limit=10:self.chats[offset:limit]
    def history(self,chat_id,offset=0,limit=10):
        ids=self.msg_ids[chat_id]
        import time
        if offset+limit>len(ids) and chat_id not in self._history_ended and time.monotonic()>=self._history_retry.get(chat_id,0):
            with self._history_lock:
                launch=chat_id not in self._history_loading and len(self._history_loading)<4
                if launch:self._history_loading.add(chat_id)
            if launch:
                def load():
                    try:
                        requested=min(100,max(30,offset+limit))
                        result=rpc(self.tg.get_chat_history(chat_id,from_message_id=ids[-1] if ids else 0,limit=requested))
                        messages=result.get('messages',[])
                        for msg in messages:
                            if msg['id'] not in self.msgs[chat_id]:self.add_message(chat_id,msg)
                        rounds=self._history_rounds.get(chat_id,0)+1 if len(messages)<requested else 0
                        self._history_rounds[chat_id]=rounds
                        if not messages and rounds>=2:self._history_ended.add(chat_id)
                    except (RuntimeError,TimeoutError):
                        self._history_retry[chat_id]=time.monotonic()+5
                        log.exception('Could not load chat history')
                    finally:
                        with self._history_lock:self._history_loading.discard(chat_id)
                        if getattr(self,'on_loaded',None):self.on_loaded()
                threading.Thread(target=load,daemon=True,name='telegram-history-loader').start()
        return [(i+offset,self.msgs[chat_id][mid]) for i,mid in enumerate(self.msg_ids[chat_id][offset:offset+limit])]
    models.MsgModel.fetch_msgs=history
    old_render_msgs=controllers.Controller._render_msgs
    def render_msgs(self):
        if getattr(self,'gallery_active',False):return
        chat_id=self.model.current_chat_id
        if chat_id is None:
            self.view.msgs.win.erase()
            self.view.msgs.win.addstr(1,2,'Загружаю чаты… Ctrl+R — повторить. Ctrl+Q — выйти.')
            self.view.msgs._refresh();return
        if not self.model.msgs.msg_ids[chat_id]:
            self.model.msgs.fetch_msgs(chat_id,limit=max(20,self.view.msgs.h))
            self.view.msgs.win.erase()
            title=self.model.chats.chats[self.model.current_chat].get('title','Переписка')
            self.view.msgs.win.addstr(0,1,title[:max(1,self.view.msgs.w-2)])
            loading=chat_id in self.model.msgs._history_loading
            note='Загружаю сообщения…' if loading else 'Сообщений пока нет. Ctrl+R — обновить.'
            self.view.msgs.win.addstr(2,2,note[:max(1,self.view.msgs.w-3)])
            self.view.msgs._refresh();return
        old_render_msgs(self)
    controllers.Controller._render_msgs=render_msgs
    old_can_send=controllers.Controller.can_send_msg
    controllers.Controller.can_send_msg=lambda self:self.model.current_chat_id is not None and old_can_send(self)
    def run(self):
        start_bootstrap(self)
        try:self.handle(controllers.chat_handler,.35)
        except Exception:log.exception('Input loop failed')
        finally:
            session_state.save(self)
            self.queue.put(lambda:quit_client(self))
    controllers.Controller.run=run
    controllers.chat_handler['^Q']=lambda self,repeat=1:quit_client(self)
    controllers.msg_handler['^Q']=controllers.chat_handler['^Q']
    controllers.msg_handler['^L']=lambda self,repeat=1:'BACK'
    controllers.chat_handler['^L']=lambda self,repeat=1:None
    controllers.chat_handler['^R']=lambda self,repeat=1:start_bootstrap(self)
    controllers.msg_handler['^R']=controllers.chat_handler['^R']
    controllers.chat_handler.pop('q',None);controllers.msg_handler.pop('q',None)
    old_keys=views.View.get_keys
    def keys(self):
        self.stdscr.timeout(200)
        ch=self.stdscr.getch()
        if ch==-1:return 1,'_TICK'
        curses.ungetch(ch);self.stdscr.timeout(-1)
        return old_keys(self)
    views.View.get_keys=keys
    old_run=app.run
    def app_run(tg,stdscr):
        from native_image import clear
        clear(stdscr,outer=True)
        try:return old_run(tg,stdscr)
        finally:
            if CURRENT:session_state.save(CURRENT)
            try:tg.stop(close_timeout=2)
            except Exception:log.exception('TDLib shutdown did not finish cleanly')
    app.run=app_run
    def finish(signum,frame):
        if CURRENT:
            engine=getattr(CURRENT,'engine',None)
            if engine:
                engine.freeze_voice()
                for voice in engine.voices.values():voice.close()
            session_state.save(CURRENT)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,finish)
    if hasattr(signal,'SIGHUP'):signal.signal(signal.SIGHUP,finish)
