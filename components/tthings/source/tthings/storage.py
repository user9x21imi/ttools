"""Cancellable read-only allocated-size scan, never follows links or mountpoints."""
import os
from pathlib import Path
import stat
import threading

class StorageScan:
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve();self.cancel=threading.Event();self.lock=threading.Lock()
        self.rows={};self.visited=0;self.errors=0;self.done=False;self.error=None;self.thread=None

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def snapshot(self):
        with self.lock:return {'path':str(self.path),'rows':sorted(self.rows.items(),key=lambda x:x[1],reverse=True),'visited':self.visited,'errors':self.errors,'done':self.done,'error':self.error,'cancelled':self.cancel.is_set()}

    def run(self):
        try:
            device=self.path.stat().st_dev
            if not self.path.is_dir():raise ValueError('Выберите папку')
            seen=set();stack=[(self.path,None)];batch=0
            while stack and not self.cancel.is_set():
                directory,group=stack.pop()
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if self.cancel.is_set():break
                            try:
                                info=entry.stat(follow_symlinks=False)
                                if stat.S_ISLNK(info.st_mode) or info.st_dev!=device:continue
                                key=(info.st_dev,info.st_ino)
                                if key in seen:continue
                                seen.add(key)
                                name=group or entry.name
                                size=getattr(info,'st_blocks',None)
                                size=info.st_size if size is None else size*512
                                with self.lock:
                                    self.rows[name]=self.rows.get(name,0)+size;self.visited+=1
                                if stat.S_ISDIR(info.st_mode):stack.append((Path(entry.path),name))
                            except OSError:
                                with self.lock:self.errors+=1
                except OSError:
                    with self.lock:self.errors+=1
        except (OSError,ValueError) as exc:self.error=str(exc)
        finally:self.done=True
