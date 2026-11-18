"""Responsive Systems Things cards: original layout, native terminal cells."""
import calendar
import datetime as dt
import math
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .effects import Frame,FG,DIM,PALETTES
from .typography import number_art,big_text

BORDER='#334759'
MUTED='#708294'

def short(text,width):
    text=str(text).replace('\n',' ')
    return text if len(text)<=max(0,width) else text[:max(0,width-1)]+'…' if width>0 else ''

def box(frame,x,y,w,h,title='',color=BORDER):
    if w<4 or h<3:return
    frame.text(x,y,'╭'+'─'*(w-2)+'╮',color);frame.text(x,y+h-1,'╰'+'─'*(w-2)+'╯',color)
    for row in range(y+1,y+h-1):frame.put(x,row,'│',color);frame.put(x+w-1,row,'│',color)
    if title:frame.text(x+2,y,' '+short(title,w-6)+' ',FG)

def blit(target,source,x,y):
    for py,row in enumerate(source.cells):
        for px,(char,color) in enumerate(row):target.put(x+px,y+py,char,color)

def gauge(frame,x,y,width,percent,color):
    width=max(1,width);value=max(0,min(100,percent or 0));n=round(value/100*width)
    frame.text(x,y,'━'*n,color);frame.text(x+n,y,'─'*(width-n),BORDER)

def card(frame,x,y,w,h,label,value,unit,color,style='blocks',size=0,footer=None,percent=None):
    box(frame,x,y,w,h,label)
    inner=max(1,w-4);max_height=max(1,h-4)
    art=number_art(str(value).replace('—','-'),inner,max_height,style,size)
    for py,row in enumerate(art.cells):
        for px,(char,_) in enumerate(row):
            if char!=' ':frame.put(x+2+px,y+2+py,char,color)
    frame.text(x+2,y+h-2,short(unit,inner),MUTED)
    if percent is not None and h>=10:gauge(frame,x+2,y+h-3,inner,percent,color)
    if footer:frame.text(x+w-len(footer)-2,y,footer,MUTED)

def plot(frame,x,y,w,h,values,color,ceiling=None):
    if w<1 or h<1:return
    values=list(values)[-w:];valid=[v for v in values if v is not None]
    peak=max(valid+[1]) if ceiling is None else max(1,ceiling)
    # Blank columns represent uncollected history, never fabricated samples.
    for row in range(h):
        if row%3==0:frame.text(x,y+row,'·'*w,'#1f303d')
    for i,value in enumerate(values):
        if value is None:continue
        bar=max(0,min(h*8,int(value/peak*h*8)));col=x+w-len(values)+i
        full,remainder=divmod(bar,8)
        for j in range(full):frame.put(col,y+h-1-j,'▒',color)
        if remainder:frame.put(col,y+h-1-full,'▁▂▃▄▅▆▇█'[remainder-1],color)

def viewport(frame,content,scroll,top=4,bottom=4):
    height=max(1,frame.h-top-bottom);offset=max(0,min(scroll,max(0,content.h-height)))
    for row in range(min(height,content.h-offset)):
        for x,(char,color) in enumerate(content.cells[offset+row]):frame.put(x,top+row,char,color)
    return frame

def render_monitor(kind,sample,width,height,history=(),scroll=0,palette=0,font_style='blocks',font_size=0,traces=None):
    from .system_ui import human,pct,rate,duration
    f=Frame(width,height);p=PALETTES[palette%len(PALETTES)];traces=traces or {}
    if not sample:
        box(f,2,4,width-4,max(4,height-9),'Системные счётчики');f.text(4,7,'Собираю первый замер…',p[0]);return f,1
    content=Frame(width,max(1,height-8));W=width-4;gap=2;cw=(W-gap)//2;top_h=10 if height>=29 else 9
    style=font_style or 'blocks';value=lambda v:'—' if v is None else str(round(v))
    def cards(a,b):
        for x,spec in [(2,a),(2+cw+gap,b)]:
            label,text,unit,col,percent=spec
            card(content,x,0,cw,top_h,label,text,unit,col,style,font_size,percent=percent)
    lower=top_h+1;lower_h=max(5,content.h-lower)
    if kind=='performance':
        cpu=sample['cpu'].get('cpu');m=sample['memory'];used,unit=human(m['used']).split()
        cards(('PROCESSOR',value(cpu),'% · загрузка CPU',p[0],cpu),('MEMORY',used,unit+' / '+human(m['total']),p[2],m['percent']))
        left=max(20,int(W*.58));right=W-left-gap
        box(content,2,lower,left,lower_h,'CPU · последние 120 с')
        plot(content,4,lower+2,left-4,max(1,lower_h-5),history,p[0],100)
        content.text(4,lower+lower_h-2,short('Uptime '+duration(sample['uptime']),left-4),MUTED)
        box(content,2+left+gap,lower,right,lower_h,'Ядра / Swap')
        cores=[(k,v) for k,v in sample['cpu'].items() if k!='cpu'];visible=max(1,lower_h-4)
        start=max(0,min(scroll,max(0,len(cores)-visible)))
        for y,(name,v) in enumerate(cores[start:start+visible],lower+2):
            xx=4+left+gap;content.text(xx,y,f'{name:<6} {pct(v):>6}',p[1]);gauge(content,xx+14,y,max(1,right-18),v,p[1])
        content.text(4+left+gap,lower+lower_h-2,short('Swap '+human(m['swap_used']),right-4),MUTED)
    elif kind in ('network','disk-io'):
        is_net=kind=='network';items=list(sample['network' if is_net else 'disks'].items())
        if is_net:
            preferred=[(name,n) for name,n in items if name not in ('lo','lo0') and n['state'] in ('up','unknown')]
            items=preferred or items
        key1,key2=('rx_bytes','tx_bytes') if is_net else ('read_bytes','write_bytes')
        if items:
            name,item=max(items,key=lambda pair:sum(pair[1]['rates'].get(k) or 0 for k in (key1,key2)))
            specs=[]
            for title,key,col in [('DOWNLOAD' if is_net else 'READ',key1,p[0]),('UPLOAD' if is_net else 'WRITE',key2,p[2] if is_net else p[4])]:
                val=item['rates'].get(key);parts=human(val).split();specs.append((title,parts[0],(parts[1]+'/s' if len(parts)>1 else 'первый замер')+' · '+name,col,None))
            cards(*specs)
            box(content,2,lower,W,lower_h,('NETWORK · '+name+' · '+item.get('state','')).upper() if is_net else 'I/O · '+name)
            hist=traces.get('network' if is_net else 'disks',{}).get(name,{})
            graph_w=max(8,(W-9)//2);graph_h=max(1,lower_h-5)
            plot(content,4,lower+2,graph_w,graph_h,hist.get(key1,[]),p[0]);plot(content,7+graph_w,lower+2,graph_w,graph_h,hist.get(key2,[]),p[2] if is_net else p[4])
            label=('Всего ↓ '+human(item['rx_bytes'])+'   ↑ '+human(item['tx_bytes'])) if is_net else ('Активность '+pct(item.get('busy_percent'))+' · устройства '+str(len(items)))
            content.text(4,lower+lower_h-2,short(label,W-4),MUTED)
        else:box(content,2,0,W,top_h,'Нет доступных устройств')
    elif kind=='disk-space':
        mounts=sample['mounts']
        if mounts:
            m=mounts[0];free=human(m['free']).split()
            cards(('STORAGE',str(round(m['percent'])),'% занято · '+m['path'],p[2],m['percent']),('AVAILABLE',free[0],free[1]+' свободно',p[0],None))
            content=Frame(width,max(content.h,lower+len(mounts)*3+3))
            cards(('STORAGE',str(round(m['percent'])),'% занято · '+m['path'],p[2],m['percent']),('AVAILABLE',free[0],free[1]+' свободно',p[0],None))
            box(content,2,lower,W,content.h-lower,'Тома')
            for i,m in enumerate(mounts):
                y=lower+2+i*3;content.text(4,y,short(m['path'],max(8,W//2)),FG);content.text(width-18,y,pct(m['percent']),p[4] if m['percent']>90 else p[2])
                gauge(content,4,y+1,max(5,W-30),m['percent'],p[2]);content.text(width-26,y+1,short(human(m['free'])+' free',20),MUTED)
    elif kind=='processes':
        procs=sorted(sample['processes'],key=lambda v:((v.get('cpu_percent') or 0),v['rss']),reverse=True)
        box(content,2,0,W,content.h,'ПРОЦЕССЫ',p[3]);content.text(4,2,f'{len(procs)} процессов · сортировка CPU / RAM',p[0])
        content.text(4,4,'PID      CPU       RAM       ПРОГРАММА',MUTED)
        available=max(1,content.h-7);start=max(0,min(scroll,max(0,len(procs)-available)))
        for y,proc in enumerate(procs[start:start+available],5):
            content.text(4,y,f"{proc['pid']:<7} {pct(proc.get('cpu_percent')):>7} {human(proc['rss']):>10}   "+short(proc['name'],W-34),FG if y%2 else p[1])
    elif kind=='sensors':
        sensors=sample['temperatures'];batteries=sample['battery']
        hottest=max(sensors,key=lambda v:v['celsius']) if sensors else None;bat=batteries[0] if batteries else None
        cards(('BATTERY',value(bat['percent']) if bat else '—','% · '+bat['status'] if bat else 'Нет батареи',p[1],bat['percent'] if bat else None),('TEMPERATURE',value(hottest['celsius']) if hottest else '—','°C · '+hottest['name'] if hottest else 'Датчики недоступны',p[4],None))
        content=Frame(width,max(content.h,lower+len(sensors)*2+3));cards(('BATTERY',value(bat['percent']) if bat else '—','% · '+bat['status'] if bat else 'Нет батареи',p[1],bat['percent'] if bat else None),('TEMPERATURE',value(hottest['celsius']) if hottest else '—','°C · '+hottest['name'] if hottest else 'Датчики недоступны',p[4],None))
        box(content,2,lower,W,content.h-lower,'Датчики')
        for i,sensor in enumerate(sensors):
            y=lower+2+i*2;content.text(4,y,short(sensor['name'],max(6,W-17)),FG);content.text(width-15,y,f"{sensor['celsius']:.1f} °C",p[4])
    viewport(f,content,scroll if kind in ('disk-space','sensors') else 0)
    return f,content.h


def render_calendar(width,height,year,month,today,style='blocks',size=0,scroll=0,year_view=False,palette=0):
    from .system_ui import MONTHS
    p=PALETTES[palette%len(PALETTES)];f=Frame(width,height)
    if year_view:
        cols=max(1,min(3,(width-4)//27));cw=(width-4-(cols-1)*2)//cols;content=Frame(width,math.ceil(12/cols)*11)
        for i,m in enumerate(range(1,13)):
            x=2+i%cols*(cw+2);y=i//cols*11;box(content,x,y,cw,10,MONTHS[m])
            lines=calendar.Calendar(0).monthdayscalendar(year,m);content.text(x+2,y+2,'Пн Вт Ср Чт Пт Сб Вс',MUTED)
            for row,week in enumerate(lines):
                for col,day in enumerate(week):
                    if day:content.text(x+2+col*3,y+3+row,f'{day:2}',p[0] if (year,m,day)==(today.year,today.month,today.day) else FG)
        return viewport(f,content,scroll)
    wide=width>=85;left=25 if wide else 0;grid_x=2+left+(2 if wide else 0);grid_w=width-grid_x-2;content=Frame(width,max(20,height-8))
    if wide:
        card(content,2,0,left,19,'СЕГОДНЯ',str(today.day),MONTHS[today.month]+' '+str(today.year),p[4],style,size)
        content.text(4,12,['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'][today.weekday()],MUTED)
    box(content,grid_x,0,grid_w,19,MONTHS[month]+' '+str(year))
    day_w=max(3,(grid_w-4)//7);start=grid_x+2;names=['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС']
    for col,name in enumerate(names):content.text(start+col*day_w+max(0,(day_w-2)//2),2,name,p[2] if col>=5 else MUTED)
    for row,week in enumerate(calendar.Calendar(0).monthdayscalendar(year,month)):
        for col,day in enumerate(week):
            if not day:continue
            is_today=(year,month,day)==(today.year,today.month,today.day);text=f'[{day:2}]' if is_today and day_w>=4 else f'{day:2}'
            x=start+col*day_w+max(0,(day_w-len(text))//2);y=4+row*2
            content.text(x,y,text,p[0] if is_today else p[2] if col>=5 else FG)
    return viewport(f,content,scroll)


def render_world_clocks(width,height,style='braille',size=0,scroll=0,palette=0):
    p=PALETTES[palette%len(PALETTES)];f=Frame(width,height);cols=3 if width>=96 else 2 if width>=60 else 1;cw=(width-4-(cols-1)*2)//cols
    glyph=number_art('23:59',max(1,cw-4),6,style,size);ch=glyph.h+4
    zones=[('UTC','UTC'),('Москва','Europe/Moscow'),('Лондон','Europe/London'),('Берлин','Europe/Berlin'),('Нью-Йорк','America/New_York'),('Токио','Asia/Tokyo')]
    content=Frame(width,max(height-8,math.ceil(len(zones)/cols)*(ch+1)))
    for i,(label,zone) in enumerate(zones):
        try:date=dt.datetime.now(ZoneInfo(zone));value=date.strftime('%H:%M');footer=date.strftime('%d.%m · %Z')
        except ZoneInfoNotFoundError:value='—';footer='Нет данных tzdata'
        card(content,2+i%cols*(cw+2),i//cols*(ch+1),cw,ch,label,value,footer,p[i%5],style,size)
    return viewport(f,content,scroll)
