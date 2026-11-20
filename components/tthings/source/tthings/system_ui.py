"""Systems Things: resize-aware dashboards and small offline utilities."""
import calendar
from collections import deque
import datetime as dt
import os
from pathlib import Path
import platform
import threading
import time
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .effects import Frame,PALETTES,FG,DIM
from .journals import Journal,KINDS,journal_dir
from .metrics import Sampler
from .storage import StorageScan
from .typography import big_text,metric_hero,STYLES,STYLE_LABELS

TITLES={'performance':'Производительность','network':'Состояние сети','disk-io':'Нагрузка дисков','disk-space':'Место на дисках','storage':'Что занимает место','processes':'Процессы','calendar':'Календарь','system-info':'О системе','sensors':'Датчики и батарея','stopwatch':'Секундомер','timezones':'Мировые часы','journals':'Журналы'}
from .system_utilities import TOOLS as UTILITY_TOOLS
TITLES.update({key:title for key,title,description in UTILITY_TOOLS})
MONITORS={'performance','network','disk-io','disk-space','processes','sensors'}
MONTHS=['','Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']

def font_control(kind,width,height):
    if kind=='system-info' and width>=60 and height>=24:return 'вид логотипа'
    if kind=='calendar' and width>=85 and height>=30:return 'шрифт даты'
    if kind in {'performance','network','disk-io','disk-space','sensors','timezones','epoch','countdown','pomodoro'} and width>=60 and height>=26:return 'шрифт цифр'
    if kind=='stopwatch' and width>=30 and height>=20:return 'шрифт цифр'
    return None


def human(value):
    if value is None:return '—'
    value=float(value)
    for unit in ['B','KiB','MiB','GiB','TiB','PiB']:
        if abs(value)<1024:return f'{value:.1f} {unit}'
        value/=1024
    return f'{value:.1f} EiB'

def pct(value):return '—' if value is None else f'{value:.1f}%'
def rate(value):return human(value)+'/s' if value is not None else '—'
def duration(value):
    if value is None:return '—'
    seconds=int(value);days,seconds=divmod(seconds,86400);hours,seconds=divmod(seconds,3600);minutes,seconds=divmod(seconds,60)
    return (f'{days}д ' if days else '')+f'{hours:02}:{minutes:02}:{seconds:02}'

def bar(value,width=24):
    n=round(max(0,min(100,value or 0))/100*width)
    return '━'*n+'─'*(width-n)

def spark(values,width=50):
    values=list(values)[-width:];peak=max([v or 0 for v in values]+[1]);chars='▁▂▃▄▅▆▇█'
    return ''.join('·' if v is None else chars[min(7,int(v/peak*7))] for v in values)

def move_month(year,month,delta):
    value=max(12,min(9999*12+11,year*12+month-1+delta))
    return value//12,value%12+1


def calendar_lines(year,month,today=None):
    today=today or dt.date.today();lines=[f'{MONTHS[month]} {year}', 'Пн Вт Ср Чт Пт Сб Вс']
    for week in calendar.Calendar(0).monthdayscalendar(year,month):
        lines.append(' '.join(f'{day:2}' if day else '  ' for day in week))
    return lines


class AsyncSamples:
    def __init__(self,processes=False):
        self.stop=threading.Event();self.lock=threading.Lock();self.latest=None;self.error=None
        self.sampler=Sampler();self.processes=processes
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.is_set():
            try:
                value=self.sampler.sample(self.processes)
                with self.lock:self.latest=value;self.error=None
            except (OSError,ValueError,RuntimeError) as exc:
                with self.lock:self.error=str(exc)
            self.stop.wait(1.)
    def read(self):
        with self.lock:return self.latest,self.error


def monitor_snapshot(kind,wait=1):
    sampler=Sampler();sampler.sample(kind=='processes')
    if wait:time.sleep(wait)
    return sampler.sample(kind=='processes')


def render_monitor(kind,sample,width,height,history=(),scroll=0,palette=0,font_style=None,font_size=0,traces=None):
    if width>=60 and height>=24:
        from .dashboard import render_monitor as draw
        return draw(kind,sample,width,height,history,scroll,palette,font_style,font_size,traces)
    return _legacy_render_monitor(kind,sample,width,height,history,scroll,palette,font_style,font_size)


def _legacy_render_monitor(kind,sample,width,height,history=(),scroll=0,palette=0,font_style=None,font_size=0):
    f=Frame(width,height);p=PALETTES[palette%len(PALETTES)]
    if not sample:f.text(2,5,'Читаю системные счётчики…',p[0]);return f,0
    lines=[]
    if kind=='performance':
        memory=sample['memory'];cpu=sample['cpu'].get('cpu')
        lines=[('CPU  '+pct(cpu)+'  '+bar(cpu,min(35,max(5,width-24))),p[0]),
               ('     '+spark(history,max(5,width-10)),p[0]),
               ('RAM  '+human(memory['used'])+' / '+human(memory['total'])+'  '+pct(memory['percent']),p[2]),
               ('     '+bar(memory['percent'],min(45,max(5,width-10))),p[2]),
               ('Swap '+human(memory['swap_used'])+' / '+human(memory['swap_total']),FG),
               ('Uptime '+duration(sample['uptime']),FG),
               ('Load  '+(' / '.join(f'{v:.2f}' for v in sample['load']) or '—'),DIM),('',DIM)]
        for name,value in sample['cpu'].items():
            if name!='cpu':lines.append((f'{name:>6}  {pct(value):>7}  '+bar(value,min(35,max(3,width-25))),p[1]))
        for gpu in sample.get('gpu',[]):lines.append((f"GPU {gpu['name']} {pct(gpu['percent'])} · VRAM {human(gpu['memory_used'])} / {human(gpu['memory_total'])}",p[2]))
        for sensor in sample['temperatures']:lines.append((f"{sensor['name']}: {sensor['celsius']:.1f} °C",p[4]))
    elif kind=='network':
        lines=[('Интерфейс          Линк      ↓ приём          ↑ передача',p[0])]
        for name,n in sample['network'].items():
            lines.extend([(f"{name[:18]:18} {n['state']:8}  {rate(n['rates']['rx_bytes']):>13}  {rate(n['rates']['tx_bytes']):>13}",FG),
                          (f"  Всего ↓ {human(n['rx_bytes'])}  ↑ {human(n['tx_bytes'])}  ошибки {n['rx_errors']}/{n['tx_errors']}  потери {n['rx_drops']}/{n['tx_drops']}",DIM),('',DIM)])
        lines.append(('Линк UP означает подключение интерфейса; доступ в интернет не проверяется.',DIM))
        lines.append(('Трафик интерфейсов VPN/мостов может учитывать те же пакеты повторно.',DIM))
        if len(sample['network'])<=1:lines.append(('Другие интерфейсы могут быть скрыты окружением или правами.',p[4]))
    elif kind=='disk-io':
        lines=[('Устройство       Чтение          Запись          IOPS     Занято',p[0])]
        for name,d in sample['disks'].items():
            rates=d['rates'];iops=None if rates['reads'] is None or rates['writes'] is None else rates['reads']+rates['writes']
            lines.append((f"{name[:15]:15} {rate(rates['read_bytes']):>14} {rate(rates['write_bytes']):>14} {('—' if iops is None else f'{iops:.0f}'):>7} {pct(d['busy_percent']):>9}",FG))
        lines.extend([('',DIM),('Занято — время активности устройства; у NVMe это не предел пропускной способности.',DIM),('Счётчики Linux: целые устройства, без повторного суммирования разделов.',DIM)])
    elif kind=='disk-space':
        for mount in sample['mounts']:
            lines.extend([(mount['path'],p[0]),(f"  {bar(mount['percent'],min(30,max(5,width-8)))}  {pct(mount['percent'])}",p[2]),
                          (f"  Занято {human(mount['used'])}   Свободно {human(mount['free'])}   Всего {human(mount['total'])}",FG),('',DIM)])
        lines.append(('Одно устройство показано один раз; повторные bind-mount не дублируются.',DIM))
    elif kind=='processes':
        lines=[('PID      CPU*       RAM        Процесс',p[0])]
        procs=sorted(sample['processes'],key=lambda p:((p['cpu_percent'] or 0),p['rss']),reverse=True)
        for proc in procs:lines.append((f"{proc['pid']:<8} {pct(proc['cpu_percent']):>8} {human(proc['rss']):>11}  {proc['name']}",FG))
        lines.append(('* CPU процесса может превышать 100% при работе на нескольких ядрах.',DIM))
    elif kind=='sensors':
        for sensor in sample['temperatures']:lines.append((f"{sensor['name']:<25} {sensor['celsius']:.1f} °C",p[4]))
        for bat in sample['battery']:lines.append((f"{bat['name']}: {pct(bat['percent'])} · {bat['status']}",p[1]))
        if not lines:lines.append(('Батарея и температурные датчики не предоставлены этой системой.',DIM))
    body_y=4
    if width>=52 and height>=24:
        defaults={'performance':'blocks','network':'dots','disk-io':'braille','disk-space':'blocks','processes':'wire','sensors':'dots'}
        style=font_style or defaults[kind];split=width>=85;column=(width-6)//2 if split else width-4
        specs=[]
        if kind=='performance':
            cpu=sample['cpu'].get('cpu');mem=sample['memory']
            specs=[('CPU',str(round(cpu))+'%' if cpu is not None else '--','Загрузка процессора',p[0]),('RAM',str(round(mem['percent']))+'%','Память · '+human(mem['used']),p[2])]
        elif kind=='network':
            choices=[(name,n) for name,n in sample['network'].items() if name not in ('lo','lo0') and n['state'] in ('up','unknown')]
            if not choices:choices=list(sample['network'].items())
            if choices:
                name,n=max(choices,key=lambda pair:sum(v or 0 for v in pair[1]['rates'].values()))
                for title,key,col in [('DOWN ↓','rx_bytes',p[0]),('UP ↑','tx_bytes',p[2])]:
                    value=n['rates'][key];label=human(value).split()
                    specs.append((title,label[0] if value is not None else '--',(label[1]+'/s · '+name) if value is not None else 'Первый замер…',col))
        elif kind=='disk-io':
            choices=list(sample['disks'].items())
            if choices:
                name,d=max(choices,key=lambda pair:sum((pair[1]['rates'].get(k) or 0) for k in ('read_bytes','write_bytes')))
                for title,key,col in [('READ','read_bytes',p[0]),('WRITE','write_bytes',p[4])]:
                    value=d['rates'][key];label=human(value).split()
                    specs.append((title,label[0] if value is not None else '--',(label[1]+'/s · '+name) if value is not None else 'Первый замер…',col))
        elif kind=='disk-space' and sample['mounts']:
            m=sample['mounts'][0];free=human(m['free']).split()
            specs=[('USED',str(round(m['percent']))+'%',m['path'],p[2]),('FREE',free[0],free[1]+' свободно',p[0])]
        elif kind=='processes':specs=[('PROCESSES',str(len(sample['processes'])),'Активные процессы',p[1])]
        elif kind=='sensors':
            if sample['battery']:
                bat=sample['battery'][0];specs=[('BATTERY',str(round(bat['percent']))+'%' if bat['percent'] is not None else '--',bat['status'],p[1])]
            elif sample['temperatures']:
                hot=max(sample['temperatures'],key=lambda v:v['celsius']);specs=[('TEMPERATURE',str(round(hot['celsius'])),hot['name']+' · °C',p[4])]
        for i,(label,value,unit,col) in enumerate(specs[:2] if split else specs[:1]):
            x=2+i*(column+2)
            secondary='braille' if style!='braille' else 'dots'
            end=metric_hero(f,label,value,unit,col,x=x,width=column,style=style if i==0 else secondary,size=min(font_size,1) if height<34 else font_size)
            body_y=max(body_y,end+1)
    available=max(1,height-body_y-5)
    offset=max(0,min(scroll,max(0,len(lines)-available)))
    for y,(line,color) in enumerate(lines[offset:offset+available],body_y):f.text(2,y,line,color)
    return f,len(lines)


def show(term,kind,palette=0,path=None,duration_limit=None,playback=None):
    from .catalog import SYSTEM_TOOLS
    ids=[e.id for e in SYSTEM_TOOLS]
    from .system_playback import SystemPlayback
    from .system_utilities import IDS as UTILITY_IDS
    playback=playback or SystemPlayback()
    if playback.palette is None:playback.palette=palette
    else:palette=playback.palette
    from .titles import system_caption
    term.set_title(system_caption(TITLES[kind]))
    scroll=0;traces={};history=deque(maxlen=120);worker=None;scan=None;sample=None;error=None;last_stamp=None
    recording=kind in KINDS;journal=Journal(kind) if recording else None;record_error=''
    today=dt.date.today();year,month=today.year,today.month;year_view=False
    started=time.monotonic();watch_started=started;watch_elapsed=0.;watch_running=True;laps=[]
    journal_index=0
    default_styles={'performance':0,'network':1,'disk-io':3,'disk-space':0,'processes':2,'sensors':1,'calendar':0,'stopwatch':1,'timezones':3,'storage':3,'journals':2}
    from .settings import read,save
    prefs=read().get('tool_styles',{});prefs=prefs if isinstance(prefs,dict) else {}
    stored=prefs.get(kind,{});stored=stored if isinstance(stored,dict) else {}
    font_index=stored.get('font',default_styles.get(kind,0));font_index=font_index if isinstance(font_index,int) and 0<=font_index<len(STYLES) else default_styles.get(kind,0)
    font_size=0  # Numeric glyph size now follows available space automatically.
    fetch=None;logo3d=None;fetch_current=None
    if kind=='system-info':
        from .system_fetch import SystemData
        fetch=SystemData()
    if kind in MONITORS:worker=AsyncSamples(kind=='processes')
    if kind=='storage':scan=StorageScan(path or Path.home());scan.start()
    try:
        while True:
            now=time.monotonic()
            if duration_limit is not None and now-playback.started>=duration_limit:return
            next_tool=playback.poll(kind,ids,now)
            if next_tool:return next_tool
            w,h=term.size();p=PALETTES[palette];f=Frame(w,h)
            if worker:
                sample,error=worker.read()
                if sample and sample['timestamp']!=last_stamp:
                    history.append(sample['cpu'].get('cpu'));last_stamp=sample['timestamp']
                    for group in ('network','disks'):
                        for name,item in sample[group].items():
                            dest=traces.setdefault(group,{}).setdefault(name,{})
                            for key,value in item.get('rates',{}).items():dest.setdefault(key,deque(maxlen=120)).append(value)
                    if recording and journal:
                        try:journal.append(sample);record_error=''
                        except (OSError,ValueError) as exc:record_error=str(exc);recording=False
                f,_=render_monitor(kind,sample,w,h,history,scroll,palette,STYLES[font_index],font_size,traces)
            elif kind in UTILITY_IDS:
                f=playback.utilities.render(kind,w,h,palette,STYLES[font_index],font_size,now)
            elif kind=='calendar':
                from .dashboard import render_calendar
                f=render_calendar(w,h,year,month,today,STYLES[font_index],font_size,scroll,year_view,palette)
                f.text(2,h-4,'←/→ месяц  ↑/↓ прокрутка  Y год  T сегодня',DIM)
            elif kind=='storage':
                state=scan.snapshot();rows=state['rows'];peak=max([v for _,v in rows]+[1]);total=sum(v for _,v in rows)
                start_row=8
                if w>=52 and h>=26:
                    value,unit=human(total).split();start_row=metric_hero(f,'STORAGE',value,unit+' на диске',p[0],width=w-4,style=STYLES[font_index],size=min(1,font_size))+3
                else:f.text(2,4,human(total),p[0])
                f.text(2,start_row-3,state['path'],p[0]);f.text(2,start_row-2,f"{state['visited']} объектов · пропущено {state['errors']}",p[1])
                f.text(2,start_row-1,state['error'] or ('Завершено' if state['done'] else 'Сканирование… Esc отменяет'),p[2])
                for y,(name,size) in enumerate(rows[scroll:scroll+max(1,h-start_row-5)],start_row):
                    f.text(2,y,f'{human(size):>11}  '+bar(size/peak*100,min(22,max(4,w//4)))+'  '+name,FG)
                f.text(2,h-4,'Размер на диске · ссылки/другие файловые системы пропускаются · R заново',DIM)
            elif kind=='system-info':
                from .system_fetch import Logo3D,render_system_info
                data,error=fetch.read()
                if data:
                    if data is not fetch_current:logo3d=Logo3D(data['logo']);fetch_current=data
                    f=render_system_info(data,w,h,now-started,logo3d,STYLES[font_index],font_size,scroll,p)
                else:f.text(2,6,error or 'Читаю сведения системы…',p[4] if error else p[0])
                f.text(2,h-4,'Встроенный каталог логотипов · данные ОС · ↑↓ список',DIM)
            elif kind=='stopwatch':
                elapsed=now-watch_started if watch_running else watch_elapsed
                label=duration(elapsed)+f'.{int(elapsed*10)%10}'
                from .typography import number_art
                art=number_art(label,max(1,w-4),max(1,h//3),STYLES[font_index],font_size)
                big_text(f,max(1,(w-art.w)//2),max(4,h//3-2),label,p[0],width=max(1,w-4),height=max(1,h//3),style=STYLES[font_index],size=font_size)
                f.text(2,h-4,'Space старт/пауза  L круг  Backspace сброс',DIM)
                for y,value in enumerate(laps[-max(1,h//3):],max(5,h//2)):f.text(3,y,f'Круг {len(laps)-len(laps[-max(1,h//3):])+y-max(5,h//2)+1}: {duration(value)}',p[2])
            elif kind=='timezones':
                from .dashboard import render_world_clocks
                f=render_world_clocks(w,h,STYLES[font_index],font_size,scroll,palette)
            elif kind=='journals':
                journal=Journal(KINDS[journal_index]);records=journal.tail(100)
                f.text(2,3,'UTC · '+str(journal.path),p[0])
                if not records:f.text(2,6,'Записей пока нет. Откройте мониторинг производительности, сети или дисков.',DIM)
                journal_x=2
                if w>=75 and h>=24:
                    metric_hero(f,'RECORDS',str(len(records)),'в текущем журнале',p[2],width=18,style=STYLES[font_index],size=font_size)
                    journal_x=24
                for y,record in enumerate(list(reversed(records))[scroll:scroll+max(1,h-12)],6):
                    stamp=record.get('timestamp','')[:19].replace('T',' ');k=record.get('kind')
                    if k=='performance':text=f"CPU {pct(record.get('cpu',{}).get('cpu'))}  RAM {pct(record.get('memory',{}).get('percent'))}"
                    elif k=='network':text=' · '.join(name+' ↓'+rate(n.get('rates',{}).get('rx_bytes'))+' ↑'+rate(n.get('rates',{}).get('tx_bytes')) for name,n in record.get('network',{}).items())
                    elif k=='disk-io':text=' · '.join(name+' R'+rate(n.get('rates',{}).get('read_bytes'))+' W'+rate(n.get('rates',{}).get('write_bytes')) for name,n in record.get('disks',{}).items())
                    else:text=' · '.join(m['path']+' '+pct(m['percent']) for m in record.get('mounts',[]))
                    f.text(journal_x,y,stamp+'  '+text,FG)
                f.text(2,h-4,'Tab — другой журнал · ↑↓ — история · последние 100 записей',DIM)
            f.text(2,1,'S Y S T E M S  T H I N G S  /  '+TITLES[kind],p[0])
            f.text(2,2,'Реальные данные системы · обновление 1 с' if worker else 'Маленькие полезные инструменты',DIM)
            if kind in KINDS:
                f.text(2,h-4,'L журнал '+('ВКЛ' if recording else 'ВЫКЛ')+'  '+str(journal.path),p[2] if recording else DIM)
            if record_error:f.text(2,h-3,'Запись остановлена: '+record_error,p[4])
            elif error:f.text(2,h-3,error,p[4])
            elif worker:f.text(2,h-3,'↑↓ прокрутка · — означает: ещё нет замера или данные недоступны',DIM)
            status=f'АВТО: {playback.auto.remaining(now)}с' if playback.auto.enabled else 'удержать R 2с: авто'
            f.text(2,h-2,f'R случайный · {status} · N следующий · Esc меню',DIM)
            font_label=font_control(kind,w,h)
            help_line='P палитра · A авто вкл/выкл'
            if font_label:help_line+=f' · F {font_label}: {STYLE_LABELS[font_index].lower()}'
            f.text(2,h-1,help_line,DIM)
            term.draw(f);key=term.read(.1)
            from .playback import canonical_key
            raw_key=key
            if key is not None:key=canonical_key(key)
            if key in ('escape','q','\x03'):return
            next_tool=playback.key(key,kind,ids,time.monotonic())
            if next_tool:return next_tool
            if key in ('r','a','n'):continue
            if kind in UTILITY_IDS and key is not None and playback.utilities.key(kind,raw_key if kind=='key-inspector' else key,time.monotonic()):continue
            if key=='f' and font_label:font_index=(font_index+1)%len(STYLES)
            elif key=='p':palette=(palette+1)%len(PALETTES);playback.palette=palette
            elif key in ('down','j'):scroll+=1
            elif key in ('up','k'):scroll=max(0,scroll-1)
            elif key=='pgdown':scroll+=max(1,h-12)
            elif key=='pgup':scroll=max(0,scroll-max(1,h-12))
            elif key in ('[',']'):
                playback.auto.reset(now)
                return ids[(ids.index(kind)+(1 if key==']' else -1))%len(ids)]
            elif key=='l' and kind in KINDS:recording=not recording
            elif kind=='calendar':
                if key=='right':year,month=move_month(year,month,12 if year_view else 1);scroll=0
                elif key=='left':year,month=move_month(year,month,-12 if year_view else -1);scroll=0
                elif key=='y':year_view=not year_view;scroll=0
                elif key=='t':year,month=today.year,today.month;scroll=0
            elif kind=='storage' and key=='r' and scan.done:scan=StorageScan(path or Path.home());scan.start()
            elif kind=='stopwatch':
                if key==' ':
                    if watch_running:watch_elapsed=now-watch_started
                    else:watch_started=now-watch_elapsed
                    watch_running=not watch_running
                elif key=='backspace':watch_elapsed=0.;watch_started=now;laps=[]
                elif key=='l':laps.append(now-watch_started if watch_running else watch_elapsed)
            elif kind=='journals' and key=='tab':journal_index=(journal_index+1)%len(KINDS);scroll=0
    finally:
        if worker:worker.stop.set();worker.thread.join(timeout=.2)
        if scan:scan.cancel.set();scan.thread.join(timeout=.2)
        if fetch:fetch.stop.set();fetch.thread.join(timeout=.2)
        try:
            settings=read();styles=settings.get('tool_styles',{});styles=styles if isinstance(styles,dict) else {}
            styles[kind]={'font':font_index,'size':font_size};settings['tool_styles']=styles;save(settings)
        except OSError:pass


def run_tool(term,kind,random_pressed=False,**kwargs):
    from .system_playback import SystemPlayback
    playback=SystemPlayback()
    if random_pressed:playback.hold.press(time.monotonic())
    while kind:kind=show(term,kind,playback=playback,**kwargs)
