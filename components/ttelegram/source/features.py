"""Interactive Telegram actions. No messages are sent without user selection."""
import array
import base64
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from tg.utils import suspend


def request(tg, data):
    result=tg._send_data(data)
    result.wait(timeout=20, raise_exc=True)
    return result.update or {}


def choose(title, items, label=str):
    # Native menus provide mouse selection and scrolling; retain the terminal
    # selector for SSH or desktops without a graphical session.
    if (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')) and not os.environ.get('TTELEGRAM_TEXT_MENUS'):
        args=['kdialog','--title','ttelegram','--menu',title]
        for i,item in enumerate(items):args.extend([str(i),label(item).replace('\n',' ')[:200]])
        if not items:return None
        try:
            result=subprocess.run(args,capture_output=True,text=True)
            if result.returncode:return None
            index=int(result.stdout.strip())
            return items[index] if 0<=index<len(items) else None
        except (OSError,ValueError):pass
    query=''; page=0; size=12
    while True:
        filtered=[item for item in items if query.casefold() in label(item).casefold()]
        pages=max(1,math.ceil(len(filtered)/size)); page=min(page,pages-1)
        chunk=filtered[page*size:(page+1)*size]
        print('\033[2J\033[H\033[1;36m'+title+'\033[0m')
        print(f'Страница {page+1}/{pages} | /текст — фильтр | n/p — страницы | Enter — отмена\n')
        for i,item in enumerate(chunk,1): print(f' {i:2}. {label(item)}')
        if not filtered: print('Ничего не найдено.')
        answer=input('\nВыберите номер: ').strip()
        if not answer or answer=='q': return None
        if answer.startswith('/'): query=answer[1:]; page=0
        elif answer=='n': page=min(pages-1,page+1)
        elif answer=='p': page=max(0,page-1)
        elif answer.isdigit() and 1<=int(answer)<=len(chunk): return chunk[int(answer)-1]


def voice_metadata(path):
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],text=True).strip())
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','8000','-'])
    samples=array.array('h'); samples.frombytes(pcm)
    if os.sys.byteorder!='little': samples.byteswap()
    peaks=[max((abs(v) for v in samples[i*len(samples)//100:(i+1)*len(samples)//100]),default=0) for i in range(100)]
    peak=max(peaks,default=1) or 1; packed=0
    for i,value in enumerate(peaks): packed |= min(31,round(value*31/peak)) << (i*5)
    return max(1,math.ceil(duration)),base64.b64encode(packed.to_bytes(63,'little')).decode()


def record_voice(self):
    if hasattr(self,'engine'):self.engine.toggle_voice();return
    if not self.can_send_msg():return self.present_error('В этот чат нельзя отправлять сообщения')
    chat_id=self.model.current_chat_id
    if chat_id is None:return
    try:
        from voice_recorder import show
        result=show(self)
        if result['action'] in ('quit','chat_list','settings'):
            self.view.status.pending_action=result['action'];return
        if result['action']!='send':return self.present_info('Запись отменена. Ничего не отправлено.')
        self.tg.send_voice(result['path'],chat_id,result['duration'],result['waveform']).wait(timeout=20,raise_exc=True)
        self.present_info('Голосовое передано Telegram для отправки')
    except (RuntimeError,OSError,ValueError,subprocess.SubprocessError,TimeoutError) as error:self.present_error(str(error))


_cache={}
def cached(tg,data):
    key=str(data); now=time.monotonic()
    if key not in _cache or now-_cache[key][0]>60: _cache[key]=(now,request(tg,data))
    return _cache[key][1]


def stickers(self,kind='recent'):
    if not self.can_send_msg():return self.present_error('В этот чат нельзя отправлять сообщения')
    chat_id=self.model.current_chat_id
    if chat_id is None:return
    try:
        from sticker_gallery import pick
        selected=pick(self,kind)
        if selected is None:return
        category,item=selected
        if category in ('quit','chats','settings'):
            self.view.status.pending_action={'quit':'quit','chats':'chat_list','settings':'settings'}[category]
            return
        if category=='upload':
            from mouse_ui import file_picker
            image=file_picker('gif')
            if image:
                self.view.status.attachments.setdefault(f'chat:{chat_id}',[]).append(image)
                self.present_info('GIF прикреплён. Enter — отправить.')
            return
        if category=='animation':
            content={'@type':'inputMessageAnimation','animation':{'@type':'inputAnimation','animation':{'@type':'inputFileId','id':item['animation']['id']},'width':item.get('width',0),'height':item.get('height',0),'duration':item.get('duration',0)}}
        else:
            content={'@type':'inputMessageSticker','sticker':{'@type':'inputSticker','sticker':{'@type':'inputFileId','id':item['sticker']['id']},'width':item.get('width',512),'height':item.get('height',512)},'emoji':item.get('emoji','')}
        request(self.tg,{'@type':'sendMessage','chat_id':chat_id,'input_message_content':content})
        self.present_info('GIF передан Telegram' if category=='animation' else 'Стикер передан Telegram')
    except (RuntimeError,OSError,KeyError,ValueError,TimeoutError) as error:self.present_error(str(error))


def forward(self):
    source=self.model.current_chat_id
    if source is None: return
    ids=list(self.model.selected[source]) or [self.model.current_msg_id]
    ids=[mid for mid in ids if mid]
    if not ids: return self.present_error('Выберите сообщение')
    try:
        for mid in ids:
            if not self.model.msg_properties(source,mid).get('can_be_forwarded'): return self.present_error('Пересылка этого сообщения запрещена')
        from overlay import open_overlay,confirm
        with open_overlay(self,'Пересылка · выберите чат и подтвердите отправку'):
            chat=choose('КУДА ПЕРЕСЛАТЬ?',self.model.chats.chats,lambda c:c.get('title','Без названия'))
            if chat is None: return
            if not confirm(self,f"Переслать {len(ids)} сообщ. в «{chat.get('title','')}»?"):return
            self.tg.forward_messages(chat['id'],source,ids).wait(timeout=20,raise_exc=True)
        self.present_info('Пересылка передана Telegram')
    except (RuntimeError,OSError,KeyError,TimeoutError) as e: self.present_error(str(e))


def install():
    from tg.controllers import msg_handler
    for key,fn in [('v',record_voice),('t',stickers),('f',forward)]:
        msg_handler[key]=lambda controller,repeat=False,fn=fn: fn(controller)
