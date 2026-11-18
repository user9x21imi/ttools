"""Native macOS adapters; Linux keeps its existing desktop tools."""
import json,re,subprocess,tempfile
from pathlib import Path

def apple(script):return subprocess.run(['osascript','-e',script],capture_output=True,text=True,timeout=30)
def choose_file():
    result=apple('return POSIX path of (choose file with prompt "ttelegram: прикрепить файл")')
    return result.stdout.strip() if result.returncode==0 else None

def choose_item(title,items,label):
    if not items:return None
    values=[f'{i}: {label(item)}' for i,item in enumerate(items)]
    literal='{'+', '.join(json.dumps(value,ensure_ascii=False) for value in values)+'}'
    result=apple('set picked to choose from list '+literal+' with prompt '+json.dumps(title,ensure_ascii=False)+'\nif picked is false then return ""\nreturn item 1 of picked')
    try:return items[int(result.stdout.split(':',1)[0])]
    except (ValueError,IndexError):return None

def clipboard():
    result=apple('try\nset files to the clipboard as alias list\nset paths to ""\nrepeat with f in files\nset paths to paths & POSIX path of f & linefeed\nend repeat\nreturn paths\non error\nreturn ""\nend try')
    paths=[Path(line) for line in result.stdout.splitlines() if Path(line).is_file()]
    if paths:return {'kind':'files','items':[{'kind':'document','path':str(path),'owned':False} for path in paths]}
    image=apple('try\nreturn the clipboard as «class PNGf»\non error\nreturn ""\nend try')
    match=re.search(r'«data PNGf([0-9a-fA-F]+)»',image.stdout)
    if match:
        data=bytes.fromhex(match.group(1))
        if len(data)>64*1024*1024:raise ValueError('Изображение больше 64 МБ')
        folder=Path.home()/'.cache/ttelegram/clipboard';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix='.png',dir=folder,delete=False) as file:file.write(data);path=file.name
        return {'kind':'image','path':path,'owned':True}
    text=subprocess.run(['pbpaste'],capture_output=True,text=True,timeout=3)
    return {'kind':'text','text':text.stdout} if text.stdout else {'kind':'empty'}
