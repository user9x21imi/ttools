"""Capture the base branch's draw function and compare it with the new PTY UI."""
import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time

SOURCE=Path(__file__).resolve().parents[1]
REPO=SOURCE.parents[2]


def legacy_runner(folder,base_ref):
    relative='components/tvpn/source/riseup-panel.py'
    result=subprocess.run(['git','-C',str(REPO),'show',f'{base_ref}:{relative}'],
                          check=True,capture_output=True,text=True)
    old_file=Path(folder)/'base_panel.py'
    old_file.write_text(result.stdout,encoding='utf-8')
    runner=Path(folder)/'run_baseline.py'
    runner.write_text('''import copy,importlib.util,sys,curses
from pathlib import Path
source=Path(sys.argv[1]); old_path=Path(sys.argv[2])
sys.path.insert(0,str(source))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
current=load('tvpn_current',source/'riseup-panel.py')
legacy=load('tvpn_base_draw',old_path)
def before(screen,model,journal,ended,choosing=None,update=None):
    preview=copy.copy(model)
    preview.demo=False
    if preview.state=='connected':preview.state='connecting'
    preview.detail='Synthetic preview · no real tunnel or exit check'
    legacy.draw(screen,preview,journal,ended,choosing,update)
    height,width=screen.getmaxyx()
    label='BEFORE / SYNTHETIC'
    screen.addnstr(0,max(2,width-len(label)-2),label,width-3,curses.color_pair(7)|curses.A_BOLD)
    screen.refresh()
current.draw=before
current.run(str(source/'demo_backend.py'),'amsterdam',demo=True)
''',encoding='utf-8')
    return runner,old_file


def record_before(source,runner,output):
    columns,rows=80,24
    pid,master=pty.fork()
    if pid==0:
        fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',rows,columns,0,0))
        env=dict(os.environ,TERM='xterm-256color',LC_ALL='C.UTF-8',PYTHONIOENCODING='utf-8',TVPN_NO_MOTION='0')
        os.execvpe(sys.executable,[sys.executable,str(runner),str(source),str(runner.parent/'base_panel.py')],env)
    fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,columns,0,0))
    started=time.monotonic();events=[];deadline=started+2.1
    while time.monotonic()<deadline:
        ready,_,_=select.select([master],[],[],min(.1,deadline-time.monotonic()))
        if not ready:continue
        try:chunk=os.read(master,65536)
        except OSError:break
        if chunk:events.append([round(time.monotonic()-started,3),'o',chunk.decode('utf-8','replace')])
    try:os.write(master,b'\x11')
    except OSError:pass
    try:os.waitpid(pid,0)
    except ChildProcessError:pass
    try:os.close(master)
    except OSError:pass
    header={'version':2,'width':columns,'height':rows,'timestamp':int(time.time()),
            'env':{'TERM':'xterm-256color','LANG':'C.UTF-8'}}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8') as handle:
        handle.write(json.dumps(header,ensure_ascii=False)+'\n')
        for event in events:handle.write(json.dumps(event,ensure_ascii=False)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-ref',default='fix/update-feed-and-refresh')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).parent/'artifacts')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='tvpn-before-capture-') as folder:
        runner,_=legacy_runner(folder,args.base_ref)
        cast=args.output_dir/'terminal'/'before-80x24.cast'
        record_before(SOURCE,runner,cast)
    from capture_terminal_visuals import png_from_cast
    visuals=args.output_dir/'visuals';visuals.mkdir(parents=True,exist_ok=True)
    before=visuals/'before-80x24.png';after=visuals/'main-80x24.png'
    png_from_cast(cast,before)
    before_data=base64.b64encode(before.read_bytes()).decode('ascii')
    after_data=base64.b64encode(after.read_bytes()).decode('ascii')
    width,height=1920,572
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
         '<rect width="100%" height="100%" fill="#101016"/>'
         '<text x="20" y="30" fill="#af87ff" font-family="monospace" font-size="20">BEFORE · integration draw</text>'
         '<text x="980" y="30" fill="#af87ff" font-family="monospace" font-size="20">AFTER · responsive draw</text>'
         f'<image x="0" y="44" width="960" height="528" href="data:image/png;base64,{before_data}"/>'
         f'<image x="960" y="44" width="960" height="528" href="data:image/png;base64,{after_data}"/>'
         '</svg>')
    svg_file=visuals/'before-after-80x24.svg';png_file=visuals/'before-after-80x24.png'
    svg_file.write_text(svg,encoding='utf-8')
    subprocess.run(['rsvg-convert','-o',str(png_file),str(svg_file)],check=True,capture_output=True)
    svg_file.unlink(missing_ok=True)
    print(f'Captured baseline and comparison to {visuals}')


if __name__=='__main__':main()
