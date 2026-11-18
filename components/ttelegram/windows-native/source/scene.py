"""Ignore byte-progress updates which cannot change the visible chat scene."""
import hashlib,json
IGNORED={'downloaded_size','downloaded_prefix_size','download_offset','is_downloading_active','uploaded_size','is_uploading_active','remote'}
def normalized(value):
    if isinstance(value,dict):return {key:normalized(item) for key,item in list(value.items()) if key not in IGNORED}
    if isinstance(value,(list,tuple)):return [normalized(item) for item in value]
    return value

def signature(controller):
    import media,ui
    model=controller.model;engine=getattr(controller,'engine',None);cid=model.current_chat_id
    chats=[(c['id'],c.get('title'),c.get('unread_count'),c.get('is_marked_as_unread'),(c.get('last_message') or {}).get('id')) for c in list(model.chats.chats)]
    index=model.get_current_chat_msg_idx() or 0
    ids=list(model.msgs.msg_ids[cid]) if cid is not None else []
    radius=max(20,controller.view.msgs.h+10)
    messages=[normalized(model.msgs.msgs[cid][mid]) for mid in ids[max(0,index-radius):index+radius] if mid in model.msgs.msgs[cid]]
    chat=model.chats.chats[model.current_chat] if cid is not None else {}
    title=controller.view.msgs._msg_title(chat) if cid is not None else ''
    base=(controller.view_mode,controller.view.stdscr.getmaxyx(),cid,index,ui.state())
    body=(base,messages,title,chat.get('last_read_inbox_message_id'),chat.get('last_read_outbox_message_id'),sorted(model.selected[cid]) if cid is not None else [],media._preview_revision)
    navigation=(base,chats,getattr(engine,'query',''),getattr(engine,'list_index',0))
    def digest(value):return hashlib.blake2b(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode(),digest_size=16).digest()
    return digest(body),digest(navigation)
