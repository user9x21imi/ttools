"""Clipboard drafts and terminal-only DOTS rendering; transmitted files stay original."""
import curses
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import hashlib
from copy import deepcopy
import os
import time
import sys
from PIL import Image,ImageOps
from native_image import synchronized,begin_frame
from tg.colors import get_color

ROOT=Path(__file__).parent


def clean_text(text):
    return ''.join(ch for ch in text.replace('\r\n','\n').replace('\r','\n').replace('\t','    ') if ch=='\n' or ch.isprintable())[:1_000_000]


def clipboard():
    try:
        proc=subprocess.run(['/usr/bin/python3',str(ROOT/'clipboard_read.py')],capture_output=True,text=True,timeout=8)
        data=json.loads(proc.stdout)
        if data['kind']=='files':
            from attachments import item_for
            data['items']=[item_for(item['path']) for item in data['items']]
        if data['kind']=='image':
            path=Path(data['path'])
            if path.stat().st_size>64*1024*1024: raise ValueError('Изображение больше 64 МБ')
            with Image.open(path) as image:
                data['width'],data['height']=image.size
            return data
        if data['kind']=='error': raise ValueError(data['error'])
        return data
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        raise ValueError(str(error) or 'Не удалось прочитать буфер обмена') from error


def forget_attachment(item):
    path=Path(item['path'])
    # Never remove a user's existing source file.
    if item.get('owned') and path.parent==Path.home()/'.cache/ttelegram/clipboard': path.unlink(missing_ok=True)


def photo_payload(path,caption=''):
    with Image.open(path) as image: width,height=image.size
    return {'@type':'inputMessagePhoto','photo':{'@type':'inputPhoto','photo':{'@type':'inputFileLocal','path':str(path)},'width':width,'height':height},'caption':{'@type':'formattedText','text':caption,'entities':[]}}


def send_attachments(controller,items,caption):
    # Send each file once; update the same draft list only after TDLib accepts it.
    while items:
        item=items[0]
        content=photo_payload(item['path'],caption) if item.get('kind')=='image' else {'@type':'inputMessageAnimation','animation':{'@type':'inputAnimation','animation':{'@type':'inputFileLocal','path':item['path']}},'caption':{'@type':'formattedText','text':caption,'entities':[]}}
        if item.get('kind')=='voice':
            result=controller.tg.send_voice(item['path'],controller.model.current_chat_id,item['duration'],item['waveform'])
            result.wait(timeout=30,raise_exc=True);items.pop(0);continue
        if item.get('kind')=='document':content={'@type':'inputMessageDocument','document':{'@type':'inputDocument','document':{'@type':'inputFileLocal','path':item['path']}},'caption':{'@type':'formattedText','text':caption,'entities':[]}}
        result=controller.tg._send_data({'@type':'sendMessage','chat_id':controller.model.current_chat_id,'input_message_content':content})
        result.wait(timeout=30,raise_exc=True)
        items.pop(0)
        # Keep cached source until TDLib finishes its asynchronous upload.
        caption=''


def dimensions(path,max_cols,max_rows):
    with Image.open(path) as image:
        width,height=ImageOps.exif_transpose(image).size
    from native_image import cell_pixels
    cell_w,cell_h=cell_pixels()
    scale=min(max_cols*cell_w/max(1,width),max_rows*cell_h/max(1,height))
    return min(max_cols,max(1,round(width*scale/cell_w))),min(max_rows,max(1,round(height*scale/cell_h)))


@lru_cache(maxsize=48)
def dot_cells(path,mtime,cols,rows):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGBA',image.size,(20,24,36,255)); background.alpha_composite(image)
        image=background.convert('RGB').resize((cols*2,rows*4),Image.Resampling.LANCZOS)
    pix=image.load(); result=[]
    dots=[(0,0,1),(0,1,2),(0,2,4),(1,0,8),(1,1,16),(1,2,32),(0,3,64),(1,3,128)]
    for y in range(rows):
        line=[]
        for x in range(cols):
            mask=0; colors=[]
            for dx,dy,bit in dots:
                rgb=pix[x*2+dx,y*4+dy]
                light=(rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722)
                if light>24:
                    mask|=bit; colors.append(rgb)
            if colors:
                rgb=[sum(c[i] for c in colors)//len(colors) for i in range(3)]
                color=16+36*round(rgb[0]/255*5)+6*round(rgb[1]/255*5)+round(rgb[2]/255*5)
                line.append((chr(0x2800+mask),color))
            else: line.append((' ',7))
        result.append(tuple(line))
    return tuple(result)


def draw_dots(win,path,y,x,cols,rows):
    max_h,max_w=win.getmaxyx()
    for dy,line in enumerate(dot_cells(str(path),Path(path).stat().st_mtime_ns,cols,rows)):
        for dx,(glyph,color) in enumerate(line):
            if y+dy>=max_h or x+dx>=max_w-1:continue
            try: win.addstr(y+dy,x+dx,glyph,get_color(color,-1))
            except curses.error: pass



def render(win,path,y,x,cols,rows):
    from settings import read
    if read().get('mode')=='native':
        from native_image import draw
        draw(win,path,y,x,cols,rows)
    else:draw_dots(win,path,y,x,cols,rows)


@lru_cache(maxsize=64)
def still_frame(path,mtime):
    try:
        with Image.open(path) as image:
            image.verify()
        return path
    except OSError:
        folder=Path.home()/'.cache/ttelegram/previews';folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(hashlib.sha256(f'{path}:{mtime}'.encode()).hexdigest()+'.png')
        if not dest.exists():
            if Path(path).suffix.lower()=='.tgs':
                command=[sys.executable,str(ROOT/'tgs_render.py'),path,str(dest)]
            else:command=['ffmpeg','-v','error','-y','-i',path,'-frames:v','1','-vf','scale=640:-1',str(dest)]
            result=subprocess.run(command,capture_output=True,timeout=8)
            if result.returncode: return None
        return str(dest)


def media_path(msg):
    paths=[]
    try:
        if msg.local_path:paths.append(msg.local_path)
    except (KeyError,TypeError):pass
    content=msg['content']
    for kind in ('sticker','animation'):
        item=content.get(kind,{})
        file=item.get(kind,{})
        if file.get('local',{}).get('path'):paths.append(file['local']['path'])
        thumb=item.get('thumbnail',{}).get('file',{})
        if thumb.get('local',{}).get('path'):paths.append(thumb['local']['path'])
    for path in paths:
        if Path(path).is_file():
            preview=still_frame(path,Path(path).stat().st_mtime_ns)
            if preview:return preview
    return None


def view_path(path):
    def display(screen):
        curses.curs_set(0);curses.mousemask(curses.ALL_MOUSE_EVENTS)
        with Image.open(path) as im:
            total=getattr(im,'n_frames',1)
            frames=[]
            if total>1:
                folder=Path.home()/'.cache/ttelegram/frames';folder.mkdir(parents=True,exist_ok=True)
                key=hashlib.sha256(f'{path}:{Path(path).stat().st_mtime_ns}'.encode()).hexdigest()
                step=max(1,total//90)
                for index in range(0,total,step):
                    im.seek(index);dest=folder/f'{key}-{index}.png'
                    if not dest.exists():im.convert('RGBA').save(dest)
                    frames.append((str(dest),max(.08,im.info.get('duration',100)/1000*step)))
            else:frames=[(str(path),1)]
        index=0
        while True:
            screen.erase();h,w=screen.getmaxyx()
            screen.addstr(0,0,'МЕДИА · q/Esc/клик — назад · o — оригинал'[:w-1])
            frame,delay=frames[index]
            cols,rows=dimensions(frame,max(2,w-3),max(2,h-3))
            screen.refresh();render(screen,frame,1,max(0,(w-cols)//2),cols,rows);screen.refresh()
            screen.timeout(round(delay*1000) if len(frames)>1 else -1)
            try:key=screen.get_wch()
            except curses.error:
                index=(index+1)%len(frames);continue
            if key in ('\x11','\x0c'):
                from recovery import CURRENT
                if CURRENT:CURRENT.view.status.pending_action='quit' if key=='\x11' else 'chat_list'
                return
            if key in ('q','\x1b','\n',curses.KEY_MOUSE):return
            if key=='o':subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    curses.wrapper(display)


def install():
    from tg import views,controllers
    from tg.msg import MsgProxy
    from tg.utils import suspend
    from workspace_mode import mode
    # Current TDLib stickers can have no thumbnail; use the actual sticker file.
    MsgProxy.fields_mapping['messageSticker']=('sticker','sticker')
    original_format=views.MsgView._format_msg
    original_draw=views.MsgView.draw
    from render_layout import collect as original_collect
    def collect(self,*args,**kwargs):
        result=original_collect(self,*args,**kwargs)
        self._draw_layout=result
        return result
    views.MsgView._collect_msgs_to_draw=collect
    def format_msg(self,msg,width_limit):
        base=original_format(self,msg,width_limit)
        if msg.content_type not in ('photo','sticker','animation'):return base
        path=media_path(msg)
        if not path:
            requested=getattr(self,'_media_requested',set())
            if msg.file_id and msg.file_id not in requested and len(requested)<128 and (msg.size or 0)<=10*1024*1024:
                requested.add(msg.file_id);self._media_requested=requested
                self.model.downloads[msg.file_id]=(msg['chat_id'],msg['id'])
                self.model.tg.download_file(file_id=msg.file_id)
            return base
        try:
            cols,rows=dimensions(path,min(80,max(8,self.w-6)),max(2,min(22,self.h//2)))
            from settings import read
            marker={'photo':'Фото','sticker':'Стикер','animation':'GIF'}[msg.content_type]+' / '+('DOTS' if read().get('mode','native')=='dots' else 'Изображение')
            return base+'\n'+marker+'\n'+('\n'.join(' '*cols for _ in range(rows)))
        except (OSError,ValueError):return base
    @synchronized
    def draw(self,current,msgs,padding,chat):
        if getattr(self,'gallery_active',False):return
        msgs=[(index,deepcopy(message)) for index,message in msgs]
        self._mouse_rows=[];self._media_hitboxes=[]
        begin_frame(self.win)
        original_draw(self,current,msgs,padding,chat)
        visible=getattr(self,'_draw_layout',[])
        by_id={message['id']:message for _,message in msgs}
        for elements,selected,line_num in visible:
            message=by_id.get(getattr(elements,'message_id',None))
            if message is None:continue
            idx=elements.message_index
            proxy=MsgProxy(message)
            kind=proxy.content_type
            path=media_path(proxy) if kind in ('photo','sticker','animation') else None
            self._mouse_rows.append((line_num,idx))
            if not path:continue
            try:
                cols,rows=dimensions(path,min(80,max(8,self.w-6)),max(2,min(22,self.h//2)))
                text=elements[3]
                marker={'photo':'Фото','sticker':'Стикер','animation':'GIF'}[kind]+' / '
                if marker not in text:continue
                label_width=sum(views.string_len_dwc(e) for e in elements[:3])
                before=text.rsplit(marker,1)[0].split('\n')
                offset=sum((views.string_len_dwc(s)+(label_width if i==0 else 0))//self.w+1 for i,s in enumerate(before[:-1]))
                top=line_num+offset+1
                if top>=1 and top+rows<=self.h:
                    self._media_hitboxes.append((top,1,rows,cols,idx))
                    self._refresh();render(self.win,path,top,1,cols,rows)
            except (OSError,ValueError,subprocess.SubprocessError):continue
        self._refresh()
    views.MsgView._format_msg=format_msg;views.MsgView.draw=draw
    original_open=controllers.msg_handler['l']
    def view_media(self):
        msg=MsgProxy(self.model.current_msg)
        if msg.content_type not in ('photo','sticker','animation'):return original_open(self,1)
        from media_viewer import show
        show(self)
    controllers.msg_handler['l']=lambda self,repeat=1:view_media(self)
    controllers.msg_handler['^J']=controllers.msg_handler['l']
