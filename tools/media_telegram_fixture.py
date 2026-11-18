"""Documentation-only Telegram backend. No TDLib client, account or network calls."""
import curses
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

folder=Path(os.environ['TTOOLS_MEDIA_DIR'])
sys.path.insert(0,os.environ['TTELEGRAM_TEST_RUNTIME'])
# Do not load the real tg account configuration even during demo imports.
original_isfile=os.path.isfile
private_config=str(Path.home()/'.config/tg/conf.py')
with patch('os.path.isfile',side_effect=lambda name:False if str(name)==private_config else original_isfile(name)):
    from tg import config
config.CONFIG_FILE=str(folder/'conf.py')
config.CONFIG_DIR=str(folder/'config')
config.FILES_DIR=str(folder/'files')
config.LOG_PATH=str(folder/'logs')
config.NOTIFY_CMD=''
import session_state,settings,ui
session_state.PATH=folder/'session.json'
settings.PATH=folder/'settings.json'
ui.CFG=folder/'layout.json'
ui.state=lambda:{'layout':'sidebar','theme':0}
# DOTS is captured as terminal text, avoiding any graphics protocol dependency.
settings.PATH.write_text('{"mode":"dots","quality":"high"}')

class Result:
    error=False
    error_info={}
    def __init__(self,value):self.update=value
    def wait(self,*args,**kwargs):return None

def user(uid):
    return {'id':uid,'first_name':{101:'Mira',202:'Alex',999:'Demo'}.get(uid,'Demo'),'last_name':'','type':{'@type':'userTypeRegular'},'status':{'@type':'userStatusRecently'}}
def picture_file():
    path=folder/'poster.png'
    return {'id':43,'size':path.stat().st_size,'local':{'path':str(path),'is_downloading_completed':True,'is_downloading_active':False}}
def sticker():return {'width':320,'height':220,'emoji':'','sticker':picture_file(),'format':{'@type':'stickerFormatWebp'}}
def message(cid):
    content={'@type':'messageText','text':{'text':'Всё, что любишь — в одном терминале. Новый tTools уже здесь.','entities':[]}}
    if cid==101:
        content={'@type':'messagePhoto','caption':{'text':'Новая палитра. Как тебе эти цвета?','entities':[]},'photo':{'sizes':[{'width':520,'height':300,'photo':picture_file()}]}}
    return {'@type':'message','id':1000+cid,'chat_id':cid,'date':int(time.time())-90,'sender_id':{'user_id':cid},'edit_date':0,'content':content}
def chat(cid,order):
    return {'id':cid,'title':{101:'tTools / Design Lab',202:'Ночной плейлист'}[cid],'positions':[{'list':{'@type':'chatListMain'},'order':str(order)}],'type':{'@type':'chatTypePrivate'},'permissions':{'can_send_basic_messages':True},'last_read_inbox_message_id':9999,'last_read_outbox_message_id':9999,'last_message':message(cid),'is_marked_as_unread':False,'unread_count':0,'notification_settings':{'mute_for':0}}
class TG:
    def _send_data(self,data):
        kind=data['@type']
        if kind in ('getRecentStickers','getFavoriteStickers'):return Result({'stickers':[sticker()]})
        if kind=='getMessageProperties':return Result({'can_be_forwarded':True})
        return Result({'@type':'ok'})
    def load_chats(self,**kwargs):return Result({'@type':'ok'})
    def get_chats(self,**kwargs):return Result({'chat_ids':[101,202]})
    def get_chat(self,cid):return Result(chat(cid,300 if cid==101 else 200))
    def get_chat_history(self,cid,**kwargs):return Result({'messages':[] if kwargs.get('from_message_id') else [message(cid)]})
    def get_me(self):return Result(user(999))
    def get_user(self,uid):return Result(user(uid))
    def add_update_handler(self,*args):pass
    def stop(self,**kwargs):pass

import client
client.app.run_tui=lambda:curses.wrapper(lambda screen:client.app.run(TG(),screen))
client.run_client()
