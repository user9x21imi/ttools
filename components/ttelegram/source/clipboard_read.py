"""Read the desktop clipboard via installed GTK/Xwayland. Prints only JSON to caller."""
import os
os.environ['GDK_BACKEND']='x11'
import json,sys,tempfile,subprocess,shutil
from pathlib import Path
from urllib.parse import urlparse,unquote
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk

def wayland():
    tool=Path(shutil.which('wl-paste') or str(Path.home()/'.local/libexec/ttelegram/wl-paste'))
    if not tool.exists() or not os.environ.get('WAYLAND_DISPLAY'):return None
    types=subprocess.run([str(tool),'--list-types'],capture_output=True,text=True,timeout=2)
    if types.returncode:return None
    offered=types.stdout.splitlines()
    image_type=next((t for t in ('image/png','image/jpeg','image/webp') if t in offered),None)
    if image_type:
        data=subprocess.run([str(tool),'--no-newline','--type',image_type],capture_output=True,timeout=4)
        if data.returncode:return None
        if len(data.stdout)>64*1024*1024:raise RuntimeError('Image too large')
        folder=Path.home()/'.cache/ttelegram/clipboard';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        ext={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[image_type]
        fd,name=tempfile.mkstemp(suffix=ext,prefix='screenshot-',dir=folder)
        with os.fdopen(fd,'wb') as out:out.write(data.stdout)
        return {'kind':'image','path':name,'owned':True}
    text_type=next((t for t in ('text/plain;charset=utf-8','text/plain','UTF8_STRING') if t in offered),None)
    if text_type:
        data=subprocess.run([str(tool),'--no-newline','--type',text_type],capture_output=True,text=True,timeout=2)
        if data.returncode==0:return {'kind':'text','text':data.stdout}
    return None


def main():
    try:
        result=wayland()
        if result:return result
    except (OSError,subprocess.SubprocessError):pass
    ok,_=Gtk.init_check()
    if not ok: raise RuntimeError('Не удалось подключиться к буферу рабочего стола')
    cb=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    image=cb.wait_for_image()
    if image:
        folder=Path.home()/'.cache/ttelegram/clipboard'; folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,name=tempfile.mkstemp(suffix='.png',prefix='screenshot-',dir=folder); os.close(fd)
        try: image.savev(name,'png',[],[])
        except Exception:
            Path(name).unlink(missing_ok=True); raise
        return {'kind':'image','path':name,'owned':True,'width':image.get_width(),'height':image.get_height()}
    from attachments import files_from_text
    items=[]
    for uri in cb.wait_for_uris() or []:
        items.extend({'kind':'document','path':str(path),'owned':False} for path in files_from_text(uri))
    if items:return {'kind':'files','items':items}
    text=cb.wait_for_text()
    if text is not None: return {'kind':'text','text':text}
    return {'kind':'empty'}
if __name__=='__main__':
    try: print(json.dumps(main(),ensure_ascii=False))
    except Exception:
        print(json.dumps({'kind':'error','error':'Буфер обмена недоступен. Скопируйте картинку или текст ещё раз.'}))
        sys.exit(1)
