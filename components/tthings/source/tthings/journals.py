"""Bounded, local, per-view JSONL journals, written only while a view is open."""
import datetime
import json
import os
from pathlib import Path
import sys

KINDS=('performance','network','disk-io','disk-space')

def journal_dir():
    if os.name=='nt':base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'tthings/logs'
    elif sys.platform=='darwin':base=Path.home()/'Library/Logs/tthings'
    else:base=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'tthings/journals'
    return base


def record_for(kind,sample):
    fields={'performance':['cpu','memory','load','uptime','temperatures','gpu'],'network':['network'],'disk-io':['disks'],'disk-space':['mounts']}[kind]
    return {'schema_version':1,'kind':kind,'timestamp':sample['timestamp'],**{k:sample.get(k) for k in fields}}


class Journal:
    def __init__(self,kind,directory=None,max_bytes=5*1024*1024):
        if kind not in KINDS:raise ValueError('Unknown journal')
        self.path=(Path(directory) if directory is not None else journal_dir())/(kind+'.jsonl');self.max_bytes=max_bytes

    def append(self,sample):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        payload=(json.dumps(record_for(self.path.stem,sample),ensure_ascii=False,allow_nan=False)+'\n').encode()
        try:rotate=self.path.stat().st_size+len(payload)>self.max_bytes
        except FileNotFoundError:rotate=False
        if rotate:
            for i in (2,1,0):
                src=self.path if i==0 else self.path.with_suffix('.jsonl.'+str(i))
                dst=self.path.with_suffix('.jsonl.'+str(i+1))
                if src.exists():src.replace(dst)
        descriptor=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        with os.fdopen(descriptor,'ab') as file:file.write(payload)

    def tail(self,limit=100):
        try:
            with self.path.open('rb') as file:
                file.seek(0,2);size=file.tell();file.seek(max(0,size-128*1024))
                if size>128*1024:file.readline()
                lines=file.read().splitlines()[-limit:]
            records=[]
            for line in lines:
                try:records.append(json.loads(line))
                except (ValueError,UnicodeError):continue
            return records
        except FileNotFoundError:return []
