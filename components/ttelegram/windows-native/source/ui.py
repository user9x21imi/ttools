#!/usr/bin/env python3
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path
from runtime import ROOT,SOCKET,command,tmux_config
CFG = Path.home()/'.config/ttelegram/layout.json'

PALETTES = [('NEON', '#67e8f9', '#c4b5fd'), ('AMBER', '#fbbf24', '#fb923c'), ('MINT', '#6ee7b7', '#93c5fd')]
def tm(*args, check=True):
    return subprocess.run(['tmux','-L',SOCKET,*args], check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
def state():
    try: return json.loads(CFG.read_text())
    except (OSError, ValueError): return {'layout':'sidebar', 'theme':0}
def save(s):
    CFG.parent.mkdir(parents=True, exist_ok=True); CFG.write_text(json.dumps(s))
def panes():
    p = tm('list-panes','-t','telegram:0','-F','#{pane_id}',check=False)
    return p.stdout.splitlines()
def style(s):
    if os.environ.get('TTELEGRAM_VT')=='1':
        import curses
        color=PALETTES[s.get('theme',0)%len(PALETTES)][1].lstrip('#')
        curses.init_color(curses.COLOR_CYAN,*(round(int(color[i:i+2],16)*1000/255) for i in (0,2,4)))
        return
    from workspace_mode import border_format
    name, accent, second = PALETTES[s['theme'] % len(PALETTES)]
    for key,val in {
        'pane-border-status':'top',
        'pane-border-format':border_format(),
        'status-style':f'bg=#111827,fg={accent}',
        'pane-border-style':'fg=#334155',
        'pane-active-border-style':f'fg={accent},bold',
        'message-style':f'bg=#1e293b,fg={accent},bold',
        'status-left':f'#[bold,fg=#3390ec]  ● TELEGRAM #[fg={second}] / {name}  ',
        'status-right':'#[fg=#94a3b8]Ctrl+O НАСТРОЙКИ | Ctrl+L ЧАТЫ | Ctrl+Q ВЫХОД  #[dim,fg=#475569]by user9x21imi#[default] ',
    }.items(): tm('set-option','-t','telegram',key,val)
def layout(s):
    if os.environ.get('TTELEGRAM_VT')=='1':return
    ps = panes()
    if not ps: return
    main=ps[0]
    for p in ps[1:]: tm('kill-pane','-t',p)
    tm('select-pane','-t',main)
def splash():
    from logo import render
    width=shutil.get_terminal_size().columns
    print('\033[2J\033[H',end='')
    print(render())
    print('\033[1;97m'+'T E L E G R A M'.center(width)+'\033[0m')
    print('\033[36m'+'ttelegram / F1 подсказки / Ctrl+O настройки'.center(width)+'\033[0m',flush=True)
    time.sleep(2)
    print('\033[2J\033[H',end='',flush=True)
def panel():
    from workspace_mode import set_mode
    set_mode("Подсказки по клавишам · F1 — скрыть")
    last_frame=None
    try:
        while True:
            s=state(); name,_,_=PALETTES[s['theme']%len(PALETTES)]
            terminal=shutil.get_terminal_size()
            cols=terminal.columns
            frame=(terminal,s['theme'])
            if frame==last_frame:
                time.sleep(.25); continue
            last_frame=frame
            lines=[f'+-- TTELEGRAM / {name} --+',
                '| WORKSPACE             |','+-----------------------+',
                ' Ctrl+G ГОЛОСОВОЕ',' Enter стоп → Enter отправить',' Ctrl+L СПИСОК ЧАТОВ',' Ctrl+Q СОХРАНИТЬ / ВЫЙТИ',' F7    СТИКЕРЫ / GIF',' Ctrl+T стикеры при вводе',' F1    help on / off',' F2    full > right > below',' F3    switch palette',' Ctrl+O НАСТРОЙКИ',' F4    settings (если доступна)',' Ctrl+V paste text / photo',' F5    zoom active pane',
                ' F6    next pane',' F8    apply client updates',' Alt + arrows : resize',' Mouse drag   : resize',
                '', '+-- TELEGRAM -----------+',
                ' Esc/↑ сообщения; i ввод',' ?     client shortcuts',' i     compose message',' a     continuous input',' Ctrl+G голосовое (всегда)',
                ' r     reply',' F7    СТИКЕРЫ (всегда)',' f     forward to chat',' y / p copy / forward',' Space select messages',' e     edit message',' /     search chats',' [ ]   previous / next chat',
                ' z     chat list on / off',' l     open chat / media',' h     back',' j k   move selection',
                '', '+-- NOTE ---------------+',
                ' Voice recording is sent', ' through the client.', ' Check its prompts before', ' confirming a message.']
            print('\033[H\033[2J',end='')
            for line in lines:
                color='\033[1;36m' if line.startswith('+') or line.startswith('|') else '\033[0;37m'
                print(color+line[:max(1,cols-1)]+'\033[0m')
            sys.stdout.flush(); time.sleep(1)
    except KeyboardInterrupt: pass

def main():
    p=argparse.ArgumentParser(description='ASCII workspace for Telegram')
    p.add_argument('--fast',action='store_true',help='Skip the splash'); p.add_argument('--panel',action='store_true'); p.add_argument('--action',choices=['help','layout','theme'])
    p.add_argument('--layout',choices=['full','sidebar']); p.add_argument('--preview',action='store_true')
    a=p.parse_args(); s=state()
    if a.panel: panel(); return
    if a.preview: splash(); return
    if a.layout:
        s['layout']=a.layout; save(s)
        if not a.action and panes(): layout(s)
    if a.action:
        if a.action=='theme': s['theme']=(s['theme']+1)%len(PALETTES); save(s); style(s)
        elif a.action=='help':tm('send-keys','-t','telegram:0.0','F1',check=False)
        else:
            s['layout']='sidebar' if s.get('layout')=='full' else 'full';save(s);layout(s)
        return
    if not sys.stdin.isatty(): raise SystemExit('Запустите ttelegram в терминале.')
    if not a.fast: splash()
    if tm('has-session','-t','telegram',check=False).returncode:
        size=shutil.get_terminal_size()
        tm('-f',str(tmux_config()),'new-session','-d','-s','telegram','-n','Telegram','-x',str(size.columns),'-y',str(size.lines),command(sys.executable,ROOT/'client.py'))
        style(s); layout(s)
    os.execvp('tmux',['tmux','-L',SOCKET,'attach-session','-d','-t','telegram'])
if __name__=='__main__': main()
