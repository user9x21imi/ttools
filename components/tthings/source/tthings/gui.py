"""Optional desktop surface; the terminal launcher itself does not need Tk."""
import random
import sys
import time
from .catalog import BUILTINS
from .effects import BG, FG, Scene
from .playback import AutoCycle,canonical_key
from .titles import effect_caption

def show(effect=None,region=False,geometry=None,close_after=None,snap=False):
    desktop_rect = None
    if region and sys.platform.startswith('linux'):
        from .region import select_desktop_region
        desktop_rect = select_desktop_region(snap=snap)
        if desktop_rect is None:
            return
        region = False
    from .snapping import window_rectangles, snap_point
    desktop_windows = window_rectangles() if snap and region else []
    try:
        import tkinter as tk
        import tkinter.font as font
        root=tk.Tk()
    except (ImportError,RuntimeError) as exc:
        raise RuntimeError('Для окна нужен Tk и графический сеанс. Используйте терминальный режим или готовую сборку с Tk.') from exc
    except Exception as exc:
        raise RuntimeError(f'Не удалось открыть окно: {exc}') from exc
    root.title('tthings · выберите область')
    root.withdraw()
    def open_scene(rect=None):
        root.withdraw()
        root.overrideredirect(bool(rect))
        root.attributes('-alpha',1.0)
        root.attributes('-topmost',False)
        root.attributes('-fullscreen',False)
        for widget in root.winfo_children():widget.destroy()
        root.unbind('<Escape>')
        name=effect or random.choice(BUILTINS).id
        root.title('tthings — '+effect_caption(name))
        if rect:
            x,y,w,h=rect
            root.geometry(f'{max(80,w)}x{max(60,h)}{x:+d}{y:+d}')
        else:root.geometry(geometry or '800x480')
        root.minsize(80,60)
        family='Consolas' if root.tk.call('tk','windowingsystem')=='win32' else 'DejaVu Sans Mono'
        mono=font.Font(family=family,size=12)
        charw=max(1,mono.measure('M'));charh=max(1,mono.metrics('linespace'))
        area=tk.Text(root,font=mono,bg=BG,fg=FG,insertwidth=0,highlightthickness=0,
                     borderwidth=0,padx=8,pady=6,wrap='none',cursor='arrow',takefocus=0)
        controls=tk.Frame(root,bg=BG)
        controls.pack(side='bottom',fill='x')
        area.pack(fill='both',expand=True)
        if rect:
            drag={}
            def start_drag(event):
                drag.update(x=event.x_root,y=event.y_root,wx=root.winfo_x(),wy=root.winfo_y(),w=root.winfo_width(),h=root.winfo_height())
                return 'break'
            def move_drag(event):
                if drag:root.geometry(f"{drag['w']}x{drag['h']}{drag['wx']+event.x_root-drag['x']:+d}{drag['wy']+event.y_root-drag['y']:+d}")
                return 'break'
            def resize_drag(event):
                if drag:root.geometry(f"{max(80,drag['w']+event.x_root-drag['x'])}x{max(60,drag['h']+event.y_root-drag['y'])}")
                return 'break'
            area.bind('<Shift-ButtonPress-1>',start_drag);area.bind('<Shift-B1-Motion>',move_drag)
            area.bind('<Shift-ButtonPress-3>',start_drag);area.bind('<Shift-B3-Motion>',resize_drag)
        state={'scene':Scene(name),'start':time.monotonic(),'paused':False,'elapsed':0.,'palette':0,'last':None,'hold':None,'hold_timer':None,'release_timer':None,'hold_toggled':False,'title':None}
        auto=AutoCycle();ids=[entry.id for entry in BUILTINS]
        def change(event=None,randomize=True):
            current=state['scene'].name
            name=random.choice([id for id in ids if id!=current]) if randomize else ids[(ids.index(current)+1)%len(ids)]
            state.update(scene=Scene(name),start=time.monotonic(),elapsed=0.,last=None)
            auto.reset(time.monotonic())
            return 'break'
        def next_scene(event=None):return change(randomize=False)
        def pause(event=None):
            if state['paused']:state['start']=time.monotonic()-state['elapsed']
            else:state['elapsed']=time.monotonic()-state['start']
            state['paused']=not state['paused']
            return 'break'
        def palette(event=None):state['palette']+=1;state['last']=None;return 'break'
        def toggle_auto(event=None):auto.toggle(time.monotonic());return 'break'
        def quit_(event=None):root.destroy();return 'break'
        def held_random():
            state['hold_timer']=None
            if state['hold'] is not None and not state['hold_toggled']:
                state['hold_toggled']=True;toggle_auto()
        def random_press(event=None):
            if state['release_timer'] is not None:
                root.after_cancel(state['release_timer']);state['release_timer']=None
            if state['hold'] is None:
                state['hold']=time.monotonic();state['hold_toggled']=False
                change();state['hold_timer']=root.after(2000,held_random)
            return 'break'
        def clear_hold():
            if state['hold_timer'] is not None:root.after_cancel(state['hold_timer'])
            state.update(hold=None,hold_timer=None,release_timer=None,hold_toggled=False)
        def random_release(event=None):
            # X11 can synthesize release/press pairs for auto-repeat. Defer release
            # briefly so repeats don't reset the two-second hold clock.
            if state['release_timer'] is not None:root.after_cancel(state['release_timer'])
            state['release_timer']=root.after(80,clear_hold)
            return 'break'
        def key_press(event):
            key=canonical_key(event.char or event.keysym)
            if key=='r':return random_press(event)
            if key=='n':return next_scene(event)
            if key==' ':return pause(event)
            if key=='p':return palette(event)
            if key=='a':return toggle_auto(event)
            if key in ('escape','q','\x11') or event.keysym=='Escape':return quit_(event)
            return 'break'
        def key_release(event):
            if canonical_key(event.char or event.keysym)=='r':return random_release(event)
            return 'break'
        # Widget bindings run BEFORE Text's class bindings; top-level bindings
        # alone cannot reliably receive keys from a focused disabled Text.
        for target in (area,root):
            target.bind('<KeyPress>',key_press)
            target.bind('<KeyRelease>',key_release)
        root.bind('<Escape>',quit_);root.bind('<Control-q>',quit_)
        area.bind('<Button-1>',lambda event:area.focus_set(),add='+')
        def focus_left(event):
            root.after(100,lambda:clear_hold() if root.focus_displayof() is None else None)
        root.bind('<FocusOut>',focus_left,add='+')
        def button(label,command):
            widget=tk.Button(controls,text=label,command=command,bg=BG,fg='#92a6b9',activebackground='#1e2b37',activeforeground=FG,relief='flat',borderwidth=0,font=('sans',9),cursor='hand2',takefocus=False,padx=8,pady=2)
            widget.pack(side='left');return widget
        next_button=button('N · Далее',next_scene)
        random_button=button('R · Случайный',None)
        random_button.bind('<ButtonPress-1>',random_press);random_button.bind('<ButtonRelease-1>',random_release)
        auto_button=button('Авто: выкл',toggle_auto)
        for widget in (next_button,random_button,auto_button):
            widget.bind('<KeyPress>',key_press);widget.bind('<KeyRelease>',key_release)
        menu=tk.Menu(root,tearoff=False)
        menu.add_command(label='Следующий эффект [N]',command=next_scene)
        menu.add_command(label='Случайный эффект [R]',command=change)
        menu.add_command(label='Автопоказ 30–120 с [A / удержать R 2 с]',command=toggle_auto)
        menu.add_command(label='Пауза [Space]',command=pause)
        menu.add_command(label='Палитра [P]',command=palette)
        menu.add_separator();menu.add_command(label='Закрыть [Esc]',command=root.destroy)
        area.bind('<Button-3>',lambda e:menu.tk_popup(e.x_root,e.y_root))
        import os, json
        from pathlib import Path
        record_dir=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'tthings/windows'
        record=record_dir/(str(os.getpid())+'.json')
        last_record=[0.]
        def record_geometry():
            if os.name=='nt' or time.monotonic()-last_record[0]<1:return
            try:
                record_dir.mkdir(parents=True,exist_ok=True)
                value={'pid':os.getpid(),'updated':time.time(),'rect':[root.winfo_x(),root.winfo_y(),root.winfo_width(),root.winfo_height()]}
                temporary=record.with_suffix('.new');temporary.write_text(json.dumps(value));temporary.replace(record)
                last_record[0]=time.monotonic()
            except OSError:pass
        def tick():
            if not root.winfo_exists():return
            record_geometry()
            now=time.monotonic()
            if auto.due(now,state['paused']):change()
            title='tthings — '+effect_caption(state['scene'].name)
            if auto.enabled:title+=f' · авто {auto.remaining(now)}с'
            if title!=state['title']:
                root.title(title);auto_button.configure(text=f'Авто: {auto.remaining(now)}с' if auto.enabled else 'Авто: выкл');state['title']=title
            w=max(1,min(240,(area.winfo_width()-16)//charw))
            h=max(1,min(100,(area.winfo_height()-12)//charh))
            t=state['elapsed'] if state['paused'] else time.monotonic()-state['start']
            if not state['paused'] or state['last']!=(w,h,state['palette']):
                frame=state['scene'].render(w,h,t,state['palette'])
                area.configure(state='normal');area.delete('1.0','end')
                for y,row in enumerate(frame.cells):
                    if y:area.insert('end','\n')
                    start=0
                    for i in range(1,len(row)+1):
                        if i==len(row) or row[i][1]!=row[start][1]:
                            color=row[start][1]
                            area.tag_configure(color,foreground=color)
                            area.insert('end',''.join(c for c,_ in row[start:i]),color)
                            start=i
                area.configure(state='disabled')
                state['last']=(w,h,state['palette'])
            root.after(70,tick)
        root.deiconify();root.lift();root.after(100,area.focus_force);root.after(100,tick)
    if region:
        root.overrideredirect(True)
        root.attributes('-topmost',True)
        # Native Tk translucency outside Linux. Keep the desktop visible.
        if sys.platform == 'darwin':
            root.attributes('-transparent', True)
            background = 'systemTransparent'
        else:
            # A nonzero alpha receives mouse input on Windows. Separate opaque
            # edge windows keep the selection visible without a tinted backdrop.
            root.attributes('-alpha', 1 / 255)
            background = '#ffffff'
        root.configure(bg=background)
        # Virtual desktop on X11; primary screen on platforms where Tk exposes only it.
        width=max(root.winfo_screenwidth(),root.winfo_vrootwidth())
        height=max(root.winfo_screenheight(),root.winfo_vrootheight())
        root.geometry(f'{width}x{height}+0+0')
        canvas=tk.Canvas(root,bg=background,highlightthickness=0,cursor='crosshair')
        canvas.pack(fill='both',expand=True)
        edges=[]
        if sys.platform != 'darwin':
            for _ in range(4):
                edge=tk.Toplevel(root)
                edge.withdraw(); edge.overrideredirect(True)
                edge.attributes('-topmost',True); edge.configure(bg='#70e1ce')
                edges.append(edge)
        def clear_edges():
            for edge in edges:edge.destroy()
            edges.clear()
        selection={'start':None,'rect':None}
        def down(e):
            selection['start']=snap_point(e.x_root,e.y_root,desktop_windows) if snap else (e.x_root,e.y_root)
            if selection['rect']:canvas.delete(selection['rect'])
            selection['rect']=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline='#70e1ce',width=3)
        def move(e):
            if selection['start']:
                x,y=selection['start']
                mx,my=snap_point(e.x_root,e.y_root,desktop_windows) if snap else (e.x_root,e.y_root)
                canvas.coords(selection['rect'],x-root.winfo_rootx(),y-root.winfo_rooty(),mx-root.winfo_rootx(),my-root.winfo_rooty())
                left,top=min(x,mx),min(y,my)
                w,h=max(1,abs(mx-x)),max(1,abs(my-y))
                for edge,(ex,ey,ew,eh) in zip(edges,[(left,top,w,2),(left,top+h,w,2),(left,top,2,h),(left+w,top,2,h)]):
                    edge.geometry(f'{ew}x{eh}{ex:+d}{ey:+d}');edge.deiconify()
        def up(e):
            if not selection['start']:return
            x,y=selection['start']
            mx,my=snap_point(e.x_root,e.y_root,desktop_windows) if snap else (e.x_root,e.y_root)
            w,h=abs(mx-x),abs(my-y)
            if w<40 or h<30:return
            rect=(int(min(x,mx)),int(min(y,my)),int(w),int(h))
            clear_edges()
            open_scene(rect)
        canvas.bind('<ButtonPress-1>',down);canvas.bind('<B1-Motion>',move);canvas.bind('<ButtonRelease-1>',up)
        root.bind('<Escape>',lambda e:root.destroy())
        root.deiconify();root.lift();root.after(200,root.focus_force)
    else:open_scene(desktop_rect)
    if close_after:root.after(int(close_after*1000),root.destroy)
    try:root.mainloop()
    finally:
        import os
        from pathlib import Path
        record=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'tthings/windows'/(str(os.getpid())+'.json')
        try:record.unlink(missing_ok=True)
        except OSError:pass
