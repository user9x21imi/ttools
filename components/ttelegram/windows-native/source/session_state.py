"""Atomic on-disk recovery of the open chat, drafts and attachment drafts."""
import json,os,threading,time
from pathlib import Path
PATH=Path.home()/'.config/ttelegram/session.json'
_lock=threading.RLock()
_last_write=0.0
_last_capture=None

def read():
    try:
        value=json.loads(PATH.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def write(value):
    with _lock:
        PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temp=PATH.with_suffix('.json.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:
            json.dump(value,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
        os.replace(temp,PATH)

def capture(controller):
    status=controller.view.status
    drafts=dict(getattr(status,'drafts',{}))
    if getattr(status,'active',False) and getattr(status,'draft_key',None):drafts[status.draft_key]=status.buffer
    attachments={key:[item for item in items if Path(item.get('path','')).is_file()] for key,items in getattr(status,'attachments',{}).items()}
    current=getattr(controller,'last_open_chat_id',None)
    if not hasattr(controller,'last_open_chat_id'):
        try:current=controller.model.current_chat_id
        except (KeyError,IndexError,AttributeError):pass
    return {'version':1,'last_chat_id':current,'drafts':drafts,'attachments':attachments,'chat_list_visible':bool(getattr(controller,'chat_list_in_msgs',True)),'saved_at':time.time()}

def save(controller,force=True):
    global _last_write,_last_capture
    now=time.monotonic()
    if not force and now-_last_write<.4:return
    value=capture(controller)
    # A blank startup must never erase the previously selected chat.
    if value['last_chat_id'] is None:value['last_chat_id']=read().get('last_chat_id')
    signature={key:item for key,item in value.items() if key!='saved_at'}
    if not force and signature==_last_capture:return
    write(value);_last_write=now;_last_capture=signature

def restore_drafts(status):
    saved=read()
    status.drafts={k:v for k,v in saved.get('drafts',{}).items() if isinstance(k,str) and isinstance(v,str)}
    status.attachments={key:[item for item in items if Path(item.get('path','')).is_file()] for key,items in saved.get('attachments',{}).items() if isinstance(items,list)}
    return saved
