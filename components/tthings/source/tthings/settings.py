import json
import os
from pathlib import Path
import tempfile

def config_path():
    if os.name=='nt':base=Path(os.environ.get('APPDATA',Path.home()/'AppData/Roaming'))
    else:base=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    return base/'tthings'/'settings.json'

def read():
    try:
        value=json.loads(config_path().read_text(encoding='utf-8'))
        if not isinstance(value,dict):return {}
        return value
    except (OSError,ValueError):return {}

def save(value):
    path=config_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.settings-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
