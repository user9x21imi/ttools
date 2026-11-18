import os
import random
import subprocess
import sys
import time
import webbrowser
from .catalog import BUILTINS, executable, search
from .playback import AutoCycle,RepeatHold,canonical_key
from .effects import Frame, Scene, PALETTES, FG, DIM
from .settings import read,save
from .terminal import Terminal

def invocation():
    if getattr(sys,'frozen',False):return [sys.executable]
    import zipfile
    from pathlib import Path
    if Path(sys.argv[0]).is_file() and zipfile.is_zipfile(sys.argv[0]):
        return [sys.executable,str(Path(sys.argv[0]).resolve())]
    return [sys.executable,str(Path(__file__).resolve().parent.parent/'run.py')]

def spawn_window(region=False,effect=None,snap=False):
    args=invocation()+(['--region'] if region else ['--window'])
    if effect:args+=['--effect',effect]
    if snap:args+=['--snap']
    kwargs={}
    if os.name=='nt':kwargs['creationflags']=0x08000000
    else:kwargs['start_new_session']=True
    # Source launches must also work when cwd is outside the project.
    from pathlib import Path
    kwargs['cwd']=str(Path.home())
    from .settings import config_path
    log=config_path().with_name('window.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('ab') as errors:
        return subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=errors,**kwargs)

def play(term,name,palette=0,fps=20,duration=None):
    scene=Scene(name);started=time.monotonic();session_started=started;elapsed=0.;paused=False;hud=True
    auto=AutoCycle();hold=RepeatHold();ids=[e.id for e in BUILTINS]
    def switch(randomize=True):
        nonlocal name,scene,started,elapsed
        name=random.choice([x for x in ids if x!=name]) if randomize else ids[(ids.index(name)+1)%len(ids)]
        scene=Scene(name);started=time.monotonic();elapsed=0.;auto.reset(started)
    while True:
        tick=time.monotonic()
        term.set_title(next(entry.title for entry in BUILTINS if entry.id==name))
        t=elapsed if paused else tick-started
        if duration is not None and tick-session_started>=duration:return
        if hold.due(tick):auto.toggle(tick)
        if auto.due(tick,paused):switch();t=0.
        w,h=term.size()
        f=scene.render(min(w,300),min(max(1,h-1 if hud else h),140),t,palette)
        out=Frame(w,h)
        for y,row in enumerate(f.cells):out.cells[y][:len(row)]=row
        if hud:
            status=f"АВТО {auto.remaining(tick)}с" if auto.enabled else 'R 2с → авто'
            out.text(1,h-1,f'{name} · {status} · N далее · R случайно · Space пауза · P цвет · Esc меню',DIM)
        term.draw(out)
        key=term.read(max(0,1/fps-(time.monotonic()-tick)))
        if key is None:continue
        key=canonical_key(key)
        if key in ('escape','q','\x03'):return
        if key=='r':
            if hold.press(time.monotonic()):switch()
        elif key in ('n','right'):switch(False)
        elif key=='a':auto.toggle(time.monotonic())
        elif key==' ':
            if paused:started=time.monotonic()-elapsed
            else:elapsed=time.monotonic()-started
            paused=not paused
        elif key=='p':palette=(palette+1)%len(PALETTES)
        elif key=='h':hud=not hud

def run():
    settings=read()
    palette=settings.get('palette',0)
    if not isinstance(palette,int):palette=0
    favorites=settings.get('favorites',[])
    if not isinstance(favorites,list):favorites=[]
    query='';editing=False;selected=0;category='Все';mode='builtin';only_fav=False
    categories=['Все']+sorted({e.category for e in search()})
    notice='';notice_until=0;preview=None;preview_id=None;preview_start=time.monotonic()
    from .system_preview import SystemPreview
    systems_preview=SystemPreview()
    windows=[]
    with Terminal() as term:
        while True:
            tick=time.monotonic()
            for child in windows[:]:
                result=child.poll()
                if result is not None:
                    windows.remove(child)
                    if result:
                        from .settings import config_path
                        notice='Окно не открылось: проверьте графический сеанс; '+str(config_path().with_name('window.log'))
                        notice_until=tick+8
            term.set_title({'builtin':'Beautiful Things','systems':'Systems Things','external':'Оригиналы'}[mode])
            if mode!='systems' and (systems_preview.worker or systems_preview.fetch):systems_preview.close()
            w,h=term.size();f=Frame(w,h);p=PALETTES[palette]
            entries=search(query,category,mode)
            if only_fav:entries=[e for e in entries if e.id in favorites]
            selected=max(0,min(selected,len(entries)-1))
            current=entries[selected] if entries else None
            f.text(2,1,'t t h i n g s',p[0])
            f.text(2,2,'Тихое место для вашего терминала',DIM)
            f.text(2,4,'1 Beautiful Things   4 Systems Things   3 Оригиналы',p[1])
            f.text(2,5,f'Tab: {category} · F избранное'+(' ✓' if only_fav else ''),DIM)
            f.text(2,6,('Поиск › ' if editing else '2 / поиск › ')+query+('▏' if editing else ''),p[0] if editing else FG)
            list_width=min(36,max(24,w//3)) if w>=85 else w-4
            rows=max(1,h-14)
            offset=max(0,selected-rows+1)
            for index,e in enumerate(entries[offset:offset+rows],offset):
                y=8+index-offset
                mark='›' if index==selected else ' '
                star='*' if e.id in favorites else ' '
                status='' if e.builtin else (' +' if executable(e) else ' ↗')
                f.text(2,y,(f'{mark} {star} {e.title}{status}')[:max(1,list_width)],p[0] if index==selected else FG)
            if current:
                if w>=85 and h>=18:
                    x=list_width+5;pw=w-x-2;ph=max(1,min(42,h-15))
                    if current.kind=='effect':
                        if preview_id!=current.id:
                            preview=Scene(current.id);preview_id=current.id;preview_start=tick
                        pf=preview.render(pw,ph,tick-preview_start,palette)
                        for y,row in enumerate(pf.cells):f.cells[8+y][x:x+pw]=row
                    elif current.kind=='tool':
                        pf=systems_preview.render(current.id,pw,ph,palette)
                        for y,row in enumerate(pf.cells):f.cells[8+y][x:x+pw]=row
                    else:
                        f.text(x,9,'ОРИГИНАЛЬНЫЙ ПРОЕКТ',p[2])
                        f.text(x,11,'Установлен' if executable(current) else 'Внешний инструмент не установлен',FG)
                        f.text(x,13,'O — открыть исходники и установку',DIM)
                        f.text(x,15,'Встроенные эффекты работают автономно',DIM)
                f.text(2,h-5,current.description[:max(1,w-4)],p[2])
            else:f.text(2,8,'Ничего не найдено. Очистите поиск или смените фильтр.',DIM)
            f.text(2,h-4,f'{len(entries)} пунктов  ·  '+{'builtin':'Beautiful Things','systems':'Systems Things','external':'Оригинальные проекты'}[mode]+'  ·  * добавить в избранное',DIM)
            f.text(2,h-3,'↑↓ выбор  Enter запуск  R случайно  G область  W окно',DIM)
            f.text(2,h-2,'Tab категория  P цвет  O исходники  Esc назад / выход',DIM)
            if notice and tick<notice_until:f.text(2,h-1,notice,p[4])
            term.draw(f)
            key=term.read(max(0,.09-(time.monotonic()-tick)))
            if key is None:continue
            if key=='\x03':break
            if editing:
                if key in ('escape','enter'):editing=False
                elif key=='backspace':query=query[:-1];selected=0
                elif len(key)==1 and key.isprintable():query+=key;selected=0
                continue
            key=canonical_key(key)
            if key in ('q','escape'):
                if query:query='';selected=0
                else:break
            elif key in ('2','/','f2'):editing=True
            elif key in ('up','k'):selected=max(0,selected-1)
            elif key in ('down','j'):selected=min(len(entries)-1,selected+1)
            elif key=='pgdown':selected=min(len(entries)-1,selected+rows)
            elif key=='pgup':selected=max(0,selected-rows)
            elif key=='tab':category=categories[(categories.index(category)+1)%len(categories)];selected=0
            elif key=='1':mode='builtin';selected=0;category='Все'
            elif key=='3':mode='external';selected=0;category='Все'
            elif key=='4':mode='systems';selected=0;category='Все'
            elif key in ('left','right'):
                modes=['builtin','systems','external'];mode=modes[(modes.index(mode)+(1 if key=='right' else -1))%3];selected=0;category='Все'
            elif key=='f':only_fav=not only_fav;selected=0
            elif key=='*' and current:
                if current.id in favorites:favorites.remove(current.id)
                else:favorites.append(current.id)
            elif key=='p':palette=(palette+1)%len(PALETTES)
            elif key=='o' and current and current.url:webbrowser.open(current.url)
            elif key in ('g','w'):
                if key=='w' and current and current.kind!='effect':
                    notice='Этот инструмент открывается через Enter в терминале';notice_until=tick+4;continue
                try:
                    # Preflight here so missing Tk is visible in the launcher.
                    import tkinter
                    windows.append(spawn_window(key=='g',current.id if key=='w' and current and current.kind=='effect' else None))
                    notice='Выделите область мышью; Esc отменяет' if key=='g' else 'Окно открыто: R случайно, P цвет, Esc закрыть'
                except (ImportError,OSError) as exc:notice=f'Не удалось открыть окно: {exc}'
                notice_until=tick+5
            elif key=='r' and mode!='systems':
                choices=[e for e in entries if e.builtin] or BUILTINS
                play(term,random.choice(choices).id,palette)
            elif key=='enter' and current:
                if current.kind=='tool':
                    from .system_ui import run_tool
                    run_tool(term,current.id,palette=palette)
                elif current.kind=='effect':play(term,current.id,palette)
                else:
                    path=executable(current)
                    if not path:
                        notice='Не установлен. O — исходники; 1 — автономные эффекты';notice_until=tick+5
                    else:
                        term.stop()
                        try:
                            args=[path,*current.command[1:]]
                            if current.id=='gh-screensaver':args=[path]
                            result=subprocess.run(args,check=False)
                            if result.returncode:notice=f'{current.title}: завершён с кодом {result.returncode}';notice_until=time.monotonic()+6
                        except OSError as exc:notice=str(exc);notice_until=time.monotonic()+6
                        finally:term.start()
    systems_preview.close()
    settings=read();settings.update(palette=palette,favorites=favorites)
    try:save(settings)
    except OSError as exc:print(f'Не удалось сохранить настройки: {exc}',file=sys.stderr)
