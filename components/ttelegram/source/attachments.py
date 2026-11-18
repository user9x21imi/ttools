"""Local files from terminal drops, shell-quoted paths and file:// URI lists."""
import shlex,re
from pathlib import Path
from urllib.parse import urlparse,unquote

def _files_from_text(text):
    text=text.strip()
    if not text:return []
    # Some terminals paste an unquoted single path containing spaces.
    candidates=[text]
    if not Path(text).expanduser().is_file():
        try:candidates=shlex.split(text)
        except ValueError:return []
    files=[]
    for item in candidates:
        if item.startswith('file://'):
            uri=urlparse(item)
            if uri.netloc not in ('','localhost'):return []
            item=unquote(uri.path)
        path=Path(item).expanduser()
        if not path.is_absolute() or not path.is_file():return []
        files.append(path)
    return files

def item_for(path):
    path=Path(path);item={'kind':'document','path':str(path),'name':path.name,'owned':False}
    if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif','.bmp'):
        from PIL import Image
        try:
            with Image.open(path) as image:
                item.update(kind='animation' if getattr(image,'is_animated',False) else 'image',width=image.width,height=image.height)
        except OSError:pass
    return item

def attach_text(status,text):
    files=files_from_text(text)
    if not files or not status.draft_key:return False
    status.attachments.setdefault(status.draft_key,[]).extend(item_for(path) for path in files)
    status.notice=f'Прикреплено файлов: {len(files)}. Enter — отправить; Ctrl+D — убрать последнее.'
    return True

def consume_drop_suffix(status):
    # A terminal may deliver a drop without bracketed-paste markers. Only accept
    # complete existing absolute file paths, after input has settled.
    text=status.buffer
    starts=[m.start() for m in re.finditer(r'''(?<!\S)(?=["']?(?:/|~/|file://))''',text)]
    for start in starts:
        if attach_text(status,text[start:]):
            status.buffer=text[:start];status.pos=len(status.buffer);return True
    return False


def files_from_text(text):
    try:return _files_from_text(text)
    except (OSError,ValueError):return []
