"""Offline fake account for --demo only; no private data or real sends."""
import sys,time,threading,json,curses,logging
from pathlib import Path
import os

import session_state
session_state.PATH=demo_path('tt-native-test-session.json')
import settings
settings.PATH=demo_path('tt-native-settings.json')
DEMO_DIR=Path(os.environ['TTELEGRAM_DEMO_DIR'])
DEMO_DIR.mkdir(parents=True,exist_ok=True)
class Result:
    error=False;error_info={}
    def __init__(self,value):self.update=value
    def wait(self,*args,**kwargs):return None

def user(uid):return {'id':uid,'first_name':'Test','last_name':str(uid),'type':{'@type':'userTypeRegular'},'status':{'@type':'userStatusRecently'}}
def message(cid):
    if cid==101:
        path=demo_path('tt-native-synthetic.png')
        if not path.exists():
            from PIL import Image
            Image.new('RGB',(400,240),'cyan').save(path)
        return {'@type':'message','id':1101,'chat_id':cid,'date':1700000000,'sender_id':{'user_id':cid},'edit_date':0,'content':{'@type':'messagePhoto','caption':{'text':'Подпись тестового изображения','entities':[]},'photo':{'sizes':[{'width':400,'height':240,'photo':{'id':3,'size':path.stat().st_size,'local':{'path':str(path),'is_downloading_completed':True,'is_downloading_active':False}}}]}}}
    return {'@type':'message','id':1000+cid,'chat_id':cid,'date':1700000000,'sender_id':{'user_id':cid},'edit_date':0,'content':{'@type':'messageText','text':{'text':'TEST MESSAGE','entities':[]}}}

def history(cid):
    from PIL import Image,ImageDraw
    items=[]
    for index in range(24):
        msg=message(cid);msg['id']=10000+index;msg['date']=1700000000+index*60
        if index%2==0:
            path=demo_path('tt-native-image-'+str(index)+'.png')
            image=Image.new('RGB',(360,240),[(240,20,20),(20,240,20),(20,20,240),(240,180,20)][index//2%4]);draw=ImageDraw.Draw(image);draw.rectangle((20,20,200,150),outline='white',width=8);draw.text((30,40),'IMAGE '+str(index),fill='black');image.save(path)
            msg['content']={'@type':'messagePhoto','caption':{'text':'TEST IMAGE '+str(index),'entities':[]},'photo':{'sizes':[{'width':360,'height':240,'photo':{'id':100+index,'size':1000,'local':{'path':str(path),'is_downloading_completed':True}}}]}}
        else:msg['content']={'@type':'messageText','text':{'text':'TEST TEXT '+str(index),'entities':[]}}
        items.append(msg)
    return sorted(items,key=lambda x:x['id'],reverse=True)
def chat(cid,order):return {'id':cid,'title':'TEST CHAT '+str(cid),'positions':[{'list':{'@type':'chatListMain'},'order':str(order)}],'type':{'@type':'chatTypePrivate'},'permissions':{'can_send_basic_messages':True},'last_read_inbox_message_id':9999,'last_read_outbox_message_id':9999,'last_message':message(cid),'is_marked_as_unread':False,'unread_count':0,'notification_settings':{'mute_for':0}}
def sticker():
    path=demo_path('tt-native-synthetic.png')
    if not path.exists():
        from PIL import Image
        Image.new('RGB',(240,240),'orange').save(path)
    return {'width':240,'height':240,'emoji':'','sticker':{'id':43,'size':1000,'local':{'path':str(path),'is_downloading_completed':True}},'format':{'@type':'stickerFormatWebp'}}
class TG:
    def send_message(self,chat_id,text):
        import recovery
        self.serial+=1;msg=message(chat_id);msg['id']=self.serial;msg['sender_id']={'user_id':999};msg['content']={'@type':'messageText','text':{'text':text,'entities':[]}}
        c=recovery.CURRENT;c.model.msgs.add_message(chat_id,msg);c.model.msgs.current_msgs[chat_id]=0;c.render()
        return Result(msg)
    def reply_message(self,chat_id,message_id,text):return self.send_message(chat_id,text)
    def view_messages(self,*args,**kwargs):return Result({"@type":"ok"})
    serial=20000
    def send_voice(self,path,chat_id,duration,waveform):
        demo_path('tt-native-voice-sent.json').write_text(json.dumps({'path':path,'chat_id':chat_id,'duration':duration,'waveform':waveform}))
        return Result({'@type':'ok'})
    def _send_data(self,data):
        kind=data['@type']
        if kind in ('getRecentStickers','getFavoriteStickers'):return Result({'stickers':[sticker()]})
        if kind=='sendMessage':
            content=data['input_message_content']
            with demo_path('tt-native-sent.jsonl').open('a') as out:out.write(json.dumps(data)+'\n')
            if content['@type'] in ('inputMessageSticker','inputMessagePhoto'):
                import recovery
                c=recovery.CURRENT;self.serial+=1
                msg={'@type':'message','id':self.serial,'chat_id':101,'date':1700000100+self.serial,'sender_id':{'user_id':999},'edit_date':0,'content':{'@type':'messageSticker','sticker':sticker()}}
                if content['@type']=='inputMessagePhoto':
                    path=Path(content['photo']['photo']['path']);msg['content']={'@type':'messagePhoto','caption':content.get('caption',{'text':'','entities':[]}), 'photo':{'sizes':[{'width':1280,'height':1600,'photo':{'id':999,'size':path.stat().st_size,'local':{'path':str(path),'is_downloading_completed':True,'downloaded_size':0},'remote':{'uploaded_size':0}}}]}}
                def update():
                    c.model.msgs.add_message(101,msg);c.model.msgs.current_msgs[101]=0;c.render()
                    for number in range(100):
                        if content['@type']=='inputMessagePhoto':
                            file=msg['content']['photo']['sizes'][0]['photo'];file['local']['downloaded_size']=number;file['remote']['uploaded_size']=number
                        c.model.chats.chats[1]['unread_count']=number
                        c.render();time.sleep(.02)
                threading.Thread(target=update,daemon=True).start()
            return Result({'@type':'ok'})
        if kind=='getMessageProperties':return Result({'can_be_forwarded':True})
        return Result({'@type':'ok'})

    def load_chats(self,**kwargs):return Result({'@type':'ok'})
    def get_chats(self,**kwargs):return Result({'chat_ids':[101,202]})
    def get_chat(self,cid):return Result(chat(cid,300 if cid==101 else 200))
    def get_chat_history(self,cid,**kwargs):return Result({'messages':[] if kwargs.get('from_message_id') else history(cid)})
    def get_me(self):return Result(user(999))
    def get_user(self,uid):return Result(user(uid))
    def add_update_handler(self,*args):pass
    def stop(self,**kwargs):pass

def safe_current_id(c):
    try:return c.model.current_msg_id
    except (IndexError,KeyError):return None

def report():
    import recovery
    while True:
        c=recovery.CURRENT
        if c:
            data={'mode':c.view_mode,'chat':c.model.current_chat_id,'active':c.view.status.active,'buffer':c.view.status.buffer,'count':len(c.model.chats.chats),'overlay':getattr(c,'gallery_active',False),'input_y':c.view.status.y,'buttons':c.view.status.buttons,'hitboxes':getattr(c.view.msgs,'_media_hitboxes',[]),'sizes':{'root':c.view.stdscr.getmaxyx(),'status':c.view.status.win.getmaxyx(),'chats':c.view.chats.win.getmaxyx(),'messages':c.view.msgs.win.getmaxyx()},'clipboard_reading':getattr(c.view.status,'clipboard_reading',False),'frames':frame_count[0],'current_id':safe_current_id(c),'queue':c.queue.qsize(),'pending':getattr(c,'_frame_pending',False),'drawn_ids':[getattr(e,'message_id',None) for e,selected,row in getattr(c.view.msgs,'_draw_layout',[]) if selected],'attachments':c.view.status.attachments,'voice':None if not getattr(getattr(c,'engine',None),'voice',None) else {'progress':c.engine.voice.progress,'played':c.engine.voice.play_seconds,'duration':c.engine.voice.play_duration,'state':c.engine.voice.state,'playing':c.engine.voice.playing,'levels':list(c.engine.voice.levels),'path':str(c.engine.voice.path)}}
            p=demo_path('tt-native-test-ready.tmp');p.write_text(json.dumps(data));p.replace(demo_path('tt-native-test-ready.json'))
        time.sleep(.05)
from PIL import Image
Image.new('RGB',(1280,1600),'steelblue').save(demo_path('tt-native-screenshot.png'))
import recovery,client,ui,media,native_image
import engine
engine.Engine.toggle_voice=lambda self:setattr(self.s,'notice','Демо: микрофон отключён. Запись проверяется отдельно на Windows.')
frame_count=[0]
original_emit=native_image.emit
def count_emit(payload):
    if payload.startswith('\x1b[?2026h'):frame_count[0]+=1
    original_emit(payload)
native_image.emit=count_emit
media.clipboard=lambda:(time.sleep(.8) or {'kind':'image','path':str(demo_path('tt-native-screenshot.png')),'owned':False,'width':1280,'height':1600})
ui.state=lambda:{'layout':'sidebar','theme':0}
threading.Thread(target=report,daemon=True).start()
client.app.run_tui=lambda:curses.wrapper(lambda screen:client.app.run(TG(),screen))
try:client.run_client()
except Exception:
    import traceback
    demo_path('tt-native-test-error').write_text(traceback.format_exc())
