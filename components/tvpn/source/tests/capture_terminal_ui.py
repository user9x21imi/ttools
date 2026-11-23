"""Record real PTY sessions of launch.py --demo as replayable asciinema v2."""
import argparse
import json
import os
from pathlib import Path
import select
import sys
import time

from test_terminal_ui import CursesPtyTests


class Recording:
    def __init__(self,columns,rows):
        self.columns,self.rows=columns,rows
        self.case=CursesPtyTests()
        self.pid,self.master=self.case.start(columns,rows)
        self.started=time.monotonic()
        self.events=[]

    def wait(self,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            ready,_,_=select.select([self.master],[],[],min(.1,deadline-time.monotonic()))
            if not ready:continue
            try:chunk=os.read(self.master,65536)
            except OSError:break
            if not chunk:break
            self.events.append([round(time.monotonic()-self.started,3),'o',chunk.decode('utf-8','replace')])

    def key(self,value):
        self.events.append([round(time.monotonic()-self.started,3),'i',value.decode('ascii','replace')])
        os.write(self.master,value)

    def close(self):
        try:self.key(b'\x11')
        except OSError:pass
        self.wait(.5)
        self.case.close(self.pid,self.master)

    def save(self,path):
        header={'version':2,'width':self.columns,'height':self.rows,
                'timestamp':int(time.time()),'env':{'TERM':'xterm-256color','LANG':'C.UTF-8'}}
        with Path(path).open('w',encoding='utf-8') as output:
            output.write(json.dumps(header,ensure_ascii=False)+'\n')
            for event in self.events:output.write(json.dumps(event,ensure_ascii=False)+'\n')


def record(path,columns,rows,scenario):
    session=Recording(columns,rows)
    try:
        if scenario=='connection':
            session.wait(2.5)
        else:
            session.wait(1.0)
        if scenario=='rotation':
            session.key(b' ')
            session.wait(2.0)
        elif scenario=='region':
            session.key(b'r');session.wait(.25)
            session.key(b'\x1bOB');session.wait(.3)
            session.key(b'\n');session.wait(3.0)
        elif scenario=='disconnect':
            session.key(b'\x13');session.wait(1.0)
        elif scenario=='connection':
            pass
        else:
            session.wait(4.0)
        session.save(path)
    finally:
        session.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).parent/'artifacts'/'terminal')
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for columns,rows in ((80,24),(120,40),(160,50)):
        record(args.output_dir/f'main-{columns}x{rows}.cast',columns,rows,'main')
    record(args.output_dir/'globe-rotation.cast',120,40,'rotation')
    record(args.output_dir/'region-transition.cast',120,40,'region')
    record(args.output_dir/'connection-demo.cast',80,24,'connection')
    record(args.output_dir/'disconnected.cast',80,24,'disconnect')
    print(f'Recorded seven actual curses PTY sessions in {args.output_dir}')


if __name__=='__main__':main()
