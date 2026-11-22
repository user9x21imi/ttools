"""Offline fake account for --demo only; no private data or real sends."""
import time,threading,json,curses,logging
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
    for index in range(120):
        msg=message(cid);msg['id']=10000+index;msg['date']=1700000000+index*60
        if index%2==0:
            path=demo_path('tt-native-image-'+str(index)+'.png')
            image=Image.new('RGB',(360,240),[(240,20,20),(20,240,20),(20,20,240),(240,180,20)][index//2%4]);draw=ImageDraw.Draw(image);draw.rectangle((20,20,200,150),outline='white',width=8);draw.text((30,40),'IMAGE '+str(index),fill='black');image.save(path)
            msg['content']={'@type':'messagePhoto','caption':{'text':'TEST IMAGE '+str(index),'entities':[]},'photo':{'sizes':[{'width':360,'height':240,'photo':{'id':100+index,'size':1000,'local':{'path':str(path),'is_downloading_completed':True}}}]}}
        else:
            text='TEST TEXT '+str(index)
            if index==31:
                text=('Длинное тестовое сообщение для проверки переноса русского текста, English words, emoji 🙂 и сохранения позиции прокрутки. ' * 12)
            msg['content']={'@type':'messageText','text':{'text':text,'entities':[]}}
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
    def get_chats(self,**kwargs):return Result({'chat_ids':[101,*range(202,219)]})
    def get_chat(self,cid):return Result(chat(cid,300 if cid==101 else 200))
    def get_chat_history(self,cid,**kwargs):return Result({'messages':[] if kwargs.get('from_message_id') else history(cid)})
    def get_me(self):return Result(user(999))
    def get_user(self,uid):return Result(user(uid))
    def add_update_handler(self,*args):pass
    def stop(self,**kwargs):pass

def safe_current_id(c):
    try:return c.model.current_msg_id
    except (IndexError,KeyError):return None

def snapshot(controller,path):
    from PIL import Image,ImageDraw,ImageFont,ImageOps
    import vtcurses
    screen=controller.view.stdscr;rows,cols=screen.getmaxyx();cell_w,cell_h=10,18
    image=Image.new('RGB',(cols*cell_w,rows*cell_h),(12,17,27));draw=ImageDraw.Draw(image)
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
    try:font=ImageFont.truetype(font_path,13)
    except OSError:font=ImageFont.load_default()
    layers=[screen]
    layers.extend(window for window,_ in getattr(controller,'_panels',[]))
    layers.extend(getattr(view.win,'win',view.win) for view in (controller.view.chats,controller.view.msgs,controller.view.status))
    palette={0:'#000000',1:'#e06c75',2:'#98c379',3:'#e5c07b',4:'#61afef',5:'#c678dd',6:'#78b7d0',7:'#cbd5e1'}
    for window in layers:
        top,left=window.getbegyx();height,width=window.getmaxyx()
        for y,line in enumerate(getattr(window,'grid',[])):
            if y>=height:break
            run_start=0;run_attr=None;run_text=[]
            def flush(end):
                if not run_text:return
                attr=run_attr or 0;pair=(attr>>8)&0xfff;fg,_=vtcurses._pairs.get(pair,(-1,-1))
                foreground=vtcurses._colors.get(fg)
                if foreground:foreground='#%02x%02x%02x'%foreground
                else:foreground=palette.get(fg,'#c8d3e1') if fg>=0 else '#c8d3e1'
                if attr&vtcurses.A_DIM:foreground='#748399'
                if attr&vtcurses.A_BOLD and fg<0:foreground='#eef5fb'
                draw.text(((left+run_start)*cell_w,(top+y)*cell_h-1),''.join(run_text),font=font,fill=foreground)
                run_text.clear()
            for x,cell in enumerate(line[:width]):
                char,attr=cell
                if char is None:
                    flush(x);run_start=x+1;run_attr=None;continue
                if run_attr is not None and attr!=run_attr:
                    flush(x);run_start=x
                elif run_attr is None:run_start=x
                run_attr=attr;run_text.append(char)
            flush(min(width,len(line)))
    message_view=controller.view.msgs
    origin_y,origin_x=message_view.win.getbegyx()
    for y,x,cols,rows,_index,media_path in getattr(message_view,'_editorial_media',[]):
        try:
            with Image.open(media_path) as source:
                media=ImageOps.exif_transpose(source).convert('RGB').resize((cols*cell_w,max(1,rows*cell_h-1)),Image.Resampling.LANCZOS)
                image.paste(media,((origin_x+x)*cell_w,(origin_y+y)*cell_h))
        except (OSError,ValueError):pass
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.part')
    image.save(temporary,format='PNG');temporary.replace(path)

def save_snapshot(controller,path):
    try:snapshot(controller,path)
    except Exception:
        import traceback
        demo_path('tt-native-test-report-error.txt').write_text(traceback.format_exc(),encoding='utf-8')

def report():
    import recovery
    captured=set();transition_key=None;transition_last=0;transition_index=0;transition_count=0;drawing_since=None;trace_dumped=False
    while True:
        c=recovery.CURRENT
        if c:
            if getattr(c,'_drawing_frame',False):
                if drawing_since is None:drawing_since=time.monotonic();trace_dumped=False
                elif time.monotonic()-drawing_since>1 and not trace_dumped:
                    import faulthandler
                    with demo_path('tt-native-test-threads.txt').open('w') as stream:faulthandler.dump_traceback(file=stream,all_threads=True)
                    trace_dumped=True
            else:drawing_since=None;trace_dumped=False
            engine=getattr(c,'engine',None)
            if engine and engine.transition_started:
                if transition_key!=engine.transition_started:
                    transition_key=engine.transition_started;transition_index=0;transition_last=0;transition_count+=1
                age=time.monotonic()-transition_key
                if transition_count==1 and 0<=age<.42 and time.monotonic()-transition_last>=.035:
                    save_snapshot(c,DEMO_DIR/'transition-frames'/f'frame-{transition_index:02d}.png')
                    transition_index+=1;transition_last=time.monotonic()
            if (c.view_mode=='chats' and c.view.chats.w
                    and len(getattr(c.view.chats,'mouse_chats',[]))>=min(10,len(c.model.chats.chats))
                    and 'list' not in captured):
                save_snapshot(c,DEMO_DIR/'artifacts'/'chat-list.png');captured.add('list')
            visible_chats=getattr(c.view.chats,'mouse_chats',[])
            if (c.view_mode=='messages' and c.view.msgs.w and not getattr(engine,'transition_started',0)
                    and getattr(c.view.msgs,'_draw_layout',[])
                    and len(visible_chats)>=min(10,len(c.model.chats.chats)) and 'conversation' not in captured):
                save_snapshot(c,DEMO_DIR/'artifacts'/'conversation.png');captured.add('conversation')
            data={
                'mode':c.view_mode,'chat':c.model.current_chat_id,'active':c.view.status.active,
                'focus':getattr(getattr(c,'engine',None),'focus',None),'buffer':c.view.status.buffer,
                'count':len(c.model.chats.chats),
                'visible_chats':len(getattr(c.view.chats,'mouse_chats',[])),
                'list_index':getattr(getattr(c,'engine',None),'list_index',0),
                'list_offset':getattr(getattr(c,'engine',None),'list_offset',0),
                'history_count':len(c.model.msgs.msg_ids.get(c.model.current_chat_id,[])) if c.model.current_chat_id is not None else 0,
                'overlay':getattr(c,'gallery_active',False),'input_y':c.view.status.y,
                'buttons':c.view.status.buttons,'hitboxes':getattr(c.view.msgs,'_media_hitboxes',[]),
                'sizes':{'root':c.view.stdscr.getmaxyx(),'status':c.view.status.win.getmaxyx(),'chats':c.view.chats.win.getmaxyx(),'messages':c.view.msgs.win.getmaxyx()},
                'clipboard_reading':getattr(c.view.status,'clipboard_reading',False),'frames':frame_count[0],
                'drawing':getattr(c,'_drawing_frame',False),
                'current_id':safe_current_id(c),'queue':c.queue.qsize(),
                'pending':getattr(c,'_frame_pending',False),
                'transition_count':transition_count,
                'drawn_ids':[getattr(e,'message_id',None) for e,selected,row in getattr(c.view.msgs,'_draw_layout',[]) if selected],
                'attachments':c.view.status.attachments,
                'voice':None if not getattr(getattr(c,'engine',None),'voice',None) else {'progress':c.engine.voice.progress,'played':c.engine.voice.play_seconds,'duration':c.engine.voice.play_duration,'state':c.engine.voice.state,'playing':c.engine.voice.playing,'levels':list(c.engine.voice.levels),'path':str(c.engine.voice.path)}
            }
            p=demo_path('tt-native-test-ready.tmp');p.write_text(json.dumps(data));p.replace(demo_path('tt-native-test-ready.json'))
        time.sleep(.025)
from PIL import Image
Image.new('RGB',(1280,1600),'steelblue').save(demo_path('tt-native-screenshot.png'))
import recovery,client,ui,media,native_image,engine
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
