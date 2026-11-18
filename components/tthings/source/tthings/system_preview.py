"""Read-only menu previews; no journals, scans or timers are started implicitly."""
import datetime as dt
import time
from .effects import Frame,PALETTES,DIM,FG
from .dashboard import render_calendar,render_world_clocks,box,card
from .system_utilities import IDS as UTILITY_IDS

class SystemPreview:
    def __init__(self):
        from .system_utilities import UtilitySuite
        self.utilities=UtilitySuite()
        self.worker=None;self.fetch=None;self.history=[];self.stamp=None;self.started=time.monotonic()
    def close(self):
        if self.worker:self.worker.stop.set()
        if self.fetch:self.fetch.stop.set()
        self.worker=None;self.fetch=None
    def render(self,kind,w,h,palette=0):
        from .system_ui import MONITORS,render_monitor,human
        p=PALETTES[palette];today=dt.date.today()
        if kind in MONITORS or kind=='storage':
            if self.worker is None:
                from .system_ui import AsyncSamples
                self.worker=AsyncSamples(True)
            sample,error=self.worker.read()
            if sample and self.stamp!=sample['timestamp']:
                self.history.append(sample['cpu'].get('cpu'));self.history=self.history[-120:];self.stamp=sample['timestamp']
            f,_=render_monitor('disk-space' if kind=='storage' else kind,sample,w,h,self.history,palette=palette)
            if kind=='storage':f.text(2,h-3,'Анализ папки запускается через Enter',DIM)
        elif kind in UTILITY_IDS:f=self.utilities.render(kind,w,h,palette)
        elif kind=='calendar':f=render_calendar(w,h,today.year,today.month,today,palette=palette)
        elif kind=='timezones':f=render_world_clocks(w,h,palette=palette)
        elif kind=='system-info':
            if self.fetch is None:
                from .system_fetch import SystemData
                self.fetch=SystemData()
            data,error=self.fetch.read()
            from .system_fetch import render_system_info
            f=render_system_info(data,w,h,time.monotonic()-self.started) if data else Frame(w,h)
            if not data:f.text(2,5,error or 'Читаю сведения ОС…',p[0])
        elif kind=='stopwatch':
            f=Frame(w,h);card(f,2,4,max(4,w-4),max(9,min(15,h-8)),'СЕКУНДОМЕР','00:00.0','Space старт · L круг · R сброс',p[0],style='dots')
        else:
            from .journals import Journal,KINDS
            f=Frame(w,h);box(f,2,4,w-4,max(4,h-8),'ЖУРНАЛЫ · только чтение')
            y=6
            for name in KINDS:
                j=Journal(name);records=j.tail(100)
                f.text(4,y,name,p[0]);f.text(4,y+1,f'{len(records)} последних записей',FG);y+=3
            f.text(4,min(h-5,y+1),'Запись включается в мониторе',DIM)
        from .system_ui import TITLES
        f.text(2,1,TITLES[kind],p[0])
        return f
