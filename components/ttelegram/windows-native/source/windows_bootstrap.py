"""Install platform adapters before importing upstream terminal views."""
import os,sys
from pathlib import Path

def install(native_td=True,configure_paths=True):
    os.environ['TTELEGRAM_VT']='1';os.environ.pop('TMUX',None);os.environ.pop('TMUX_PANE',None)
    import vtcurses
    sys.modules['curses']=vtcurses
    # Upstream views import window directly from the extension module.
    # Both imports must resolve to the same VT adapter on native Windows.
    sys.modules['_curses']=vtcurses
    if native_td:
        from native_tdjson import TDJson
        import telegram.tdjson,telegram.client
        telegram.tdjson.TDJson=TDJson;telegram.client.TDJson=TDJson
    import tg.__main__ as app
    def run(tg,screen):
        import signal,threading
        from functools import partial
        from tg import config,update_handlers
        from tg.models import Model
        from tg.views import View,ChatView,MsgView,StatusView
        from tg.controllers import Controller
        signal.signal(signal.SIGINT,lambda *args:None)
        model=Model(tg);view=View(screen,ChatView(screen,model),MsgView(screen,model),StatusView(screen));controller=Controller(model,view,tg)
        for name,handler in update_handlers.handlers.items():tg.add_update_handler(name,partial(handler,controller))
        thread=threading.Thread(target=controller.run,daemon=True);thread.start();controller.draw()
    app.run=run
    from tg import utils,config
    utils.cleanup_cache=lambda:None
    if os.name=='nt':
        # Keep Cyrillic log messages readable regardless of the Windows ANSI code page.
        import logging.handlers
        from windows_desktop import copy_text
        from tg import models,controllers
        utils.copy_to_clipboard=copy_text;models.copy_to_clipboard=copy_text
        utils.notify=lambda *args,**kwargs:None;controllers.notify=utils.notify
        def setup_log():
            Path(config.LOG_PATH).mkdir(parents=True,exist_ok=True)
            handler=logging.handlers.RotatingFileHandler(str(Path(config.LOG_PATH)/'client.log'),maxBytes=8*1024*1024,backupCount=1,encoding='utf-8')
            logging.basicConfig(handlers=[handler],level=config.LOG_LEVEL,force=True)
        utils.setup_log=setup_log
    if configure_paths:
        data=Path(os.environ.get('TTELEGRAM_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ttools/ttelegram-data');data.mkdir(parents=True,exist_ok=True)
        config.FILES_DIR=str(data/'tdlib');config.LOG_PATH=str(data/'logs');config.DOWNLOAD_DIR=str(Path.home()/'Downloads');config.TDLIB_PATH=None
        import session_state,settings,ui
        session_state.PATH=data/'session.json';settings.PATH=data/'media.json';ui.CFG=data/'layout.json'
    if os.name=='nt':
        import voice_inline,windows_audio
        voice_inline.InlineVoice=windows_audio.InlineVoice
    return app
