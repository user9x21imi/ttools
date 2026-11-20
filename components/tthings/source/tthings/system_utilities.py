"""Portable offline utilities. Timers live within a Systems Things session."""
import ast
import datetime as dt
import math
import operator
import time
from .effects import Frame,FG,DIM,PALETTES
from .dashboard import box,card,gauge,short

TOOLS=[
('pomodoro','Помодоро','Фокус 25 минут, перерыв 5 минут; Space старт/пауза'),
('countdown','Таймер','Обратный отсчёт; ←→ минуты, Space старт/пауза'),
('date-progress','Ход времени','Прогресс дня, недели, месяца и года'),
('epoch','Unix-время','Unix timestamp, UTC, местное время и ISO-неделя'),
('color-lab','Лаборатория цвета','Палитра, RGB/HEX и проверка цветов терминала'),
('key-inspector','Коды клавиш','Просмотр полученных терминалом клавиш и Unicode'),
('calculator','Калькулятор','Арифметика, скобки, sqrt/sin/cos/log; Enter вычислить'),
('unit-converter','Конвертер единиц','Байты, длина, температура и время; Tab смена режима'),
]
IDS={item[0] for item in TOOLS}


def calculate(text):
    if len(text)>100:raise ValueError('Слишком длинное выражение')
    tree=ast.parse(text,mode='eval')
    binary={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod,ast.Pow:operator.pow}
    funcs={'sqrt':math.sqrt,'sin':math.sin,'cos':math.cos,'log':math.log,'abs':abs}
    def visit(node,depth=0):
        if depth>16:raise ValueError('Слишком много вложенных скобок')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):result=float(node.value)
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):result=visit(node.operand,depth+1)*(1 if isinstance(node.op,ast.UAdd) else -1)
        elif isinstance(node,ast.BinOp) and type(node.op) in binary:
            a=visit(node.left,depth+1);b=visit(node.right,depth+1)
            if isinstance(node.op,ast.Pow) and (abs(b)>100 or abs(a)>1e12):raise ValueError('Степень слишком велика')
            result=binary[type(node.op)](a,b)
        elif isinstance(node,ast.Name) and node.id in ('pi','e'):result=getattr(math,node.id)
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in funcs and len(node.args)==1 and not node.keywords:result=funcs[node.func.id](visit(node.args[0],depth+1))
        else:raise ValueError('Только арифметика и sqrt/sin/cos/log/abs')
        if not isinstance(result,(int,float)) or not math.isfinite(result) or abs(result)>1e100:raise ValueError('Результат вне диапазона')
        return result
    return visit(tree.body)


class SessionTimer:
    def __init__(self,seconds):self.total=seconds;self.remaining=seconds;self.deadline=None
    def value(self,now):return max(0,self.deadline-now) if self.deadline is not None else self.remaining
    def toggle(self,now):
        if self.deadline is None:
            if self.remaining<=0:self.remaining=self.total
            self.deadline=now+self.remaining
        else:self.remaining=self.value(now);self.deadline=None
    def reset(self):self.remaining=self.total;self.deadline=None


class UtilitySuite:
    def __init__(self):
        self.timer=SessionTimer(300);self.pomodoro=SessionTimer(1500);self.focus=True;self.rounds=0
        self.function_index=0;self.expression='';self.result='Введите выражение';self.number='1024';self.units=0;self.last_key=None
    def update(self,now):
        if self.timer.deadline is not None and now>=self.timer.deadline:self.timer.remaining=0;self.timer.deadline=None
        timer=self.pomodoro
        # Preserve the cadence while a different system tool is visible.
        while timer.deadline is not None and now>=timer.deadline:
            if self.focus:self.rounds+=1
            self.focus=not self.focus;timer.total=1500 if self.focus else 300
            timer.remaining=timer.total;timer.deadline+=timer.total
    def key(self,kind,key,now):
        if kind in ('countdown','pomodoro'):
            timer=self.timer if kind=='countdown' else self.pomodoro
            if key==' ':timer.toggle(now);return True
            if key=='backspace':timer.reset();return True
            if kind=='countdown' and key in ('left','right') and timer.deadline is None:
                timer.total=max(60,min(86400,timer.total+(60 if key=='right' else -60)));timer.reset();return True
        elif kind=='key-inspector':self.last_key=key;return True
        elif kind=='calculator':
            if key=='tab':
                self.expression+=['sqrt(','sin(','cos(','log(','abs('][self.function_index%5];self.function_index+=1;return True
            if key=='enter':
                try:self.result=f'{calculate(self.expression):.12g}'
                except (ValueError,SyntaxError,ZeroDivisionError,OverflowError) as exc:self.result='Ошибка: '+str(exc)
                return True
            if key=='backspace':self.expression=self.expression[:-1];return True
            if len(key)==1 and key in '0123456789.+-*/%() abcdefghijklmnopqrstuvwxyz' and len(self.expression)<100:self.expression+=key;return True
        elif kind=='unit-converter':
            if key=='tab':self.units=(self.units+1)%4;return True
            if key=='backspace':self.number=self.number[:-1];return True
            if len(key)==1 and key in '0123456789.-' and len(self.number)<18:self.number+=key;return True
        return False
    def render(self,kind,w,h,palette=0,style='blocks',size=0,now=None,wall=None):
        now=time.monotonic() if now is None else now;wall=wall or dt.datetime.now().astimezone();self.update(now)
        f=Frame(w,h);p=PALETTES[palette];width=max(4,w-4);height=max(9,min(15,h-9));inner=max(1,w-8)
        def lines(rows,start=7):
            for y,text in enumerate(rows,start):f.text(4,y,short(text,inner),FG)
        if kind in ('countdown','pomodoro'):
            timer=self.timer if kind=='countdown' else self.pomodoro;seconds=timer.value(now)
            mins,secs=divmod(max(0,math.ceil(seconds)),60);label=f'{mins:02}:{secs:02}'
            status='ГОТОВО' if seconds<=0 else 'ИДЁТ' if timer.deadline is not None else 'ПАУЗА'
            caption='ТАЙМЕР' if kind=='countdown' else 'ФОКУС' if self.focus else 'ПЕРЕРЫВ'
            card(f,2,4,width,height,caption,label,status,p[0],style,size,percent=(1-seconds/timer.total)*100)
            y=4+height+1
            if kind=='pomodoro':f.text(4,y,f'Завершено фокус-сессий: {self.rounds}',p[2]);y+=1
            f.text(2,min(h-4,y),'Space старт/пауза · Backspace сброс'+(' · ←→ минуты' if kind=='countdown' else ''),DIM)
        elif kind=='date-progress':
            fraction=(wall.hour*3600+wall.minute*60+wall.second)/86400
            import calendar
            values=[('ДЕНЬ',fraction),('НЕДЕЛЯ',(wall.weekday()+fraction)/7),('МЕСЯЦ',(wall.day-1+fraction)/calendar.monthrange(wall.year,wall.month)[1]),('ГОД',(wall.timetuple().tm_yday-1+fraction)/(366 if calendar.isleap(wall.year) else 365))]
            box(f,2,4,width,max(4,min(h-8,19)),'ХОД ВРЕМЕНИ')
            for i,(name,value) in enumerate(values):
                y=6+i*3;f.text(4,y,f'{name:<10} {value*100:6.2f} %',p[i]);gauge(f,4,y+1,max(1,w-8),value*100,p[i])
        elif kind=='epoch':
            card(f,2,4,width,height,'UNIX TIME',str(int(wall.timestamp())),'секунд с 1970-01-01 UTC',p[1],style,size)
            lines([wall.astimezone(dt.timezone.utc).strftime('UTC   %Y-%m-%d %H:%M:%S'),wall.strftime('LOCAL %Y-%m-%d %H:%M:%S %Z'),f'ISO-неделя {wall.isocalendar().week} · день года {wall.timetuple().tm_yday}'],5+height)
        elif kind=='color-lab':
            box(f,2,4,width,max(4,h-8),'RGB / HEX · P следующая палитра')
            for i,color in enumerate(p):
                y=6+i*3;f.text(4,y,'█'*max(1,min(12,w-8)),color)
                rgb=tuple(int(color[j:j+2],16) for j in (1,3,5));f.text(4+min(14,max(0,w-28)),y+1,short(f'{color.upper()}   RGB {rgb}',inner),color)
        elif kind=='key-inspector':
            box(f,2,4,width,max(4,h-8),'КОДЫ КЛАВИШ')
            key=self.last_key
            lines(['Нажмите клавишу…'] if key is None else [f'Получено: {key!r}',*['U+%04X  %s'%(ord(ch),repr(ch)) for ch in key[:8]]])
            f.text(4,h-5,'Esc выход · R/N/A — управление показом',DIM)
        elif kind=='calculator':
            box(f,2,4,width,max(4,h-8),'КАЛЬКУЛЯТОР')
            lines(['› '+self.expression+'▏'],6);lines(['= '+self.result],10)
            f.text(4,h-5,'Enter вычислить · Tab функция · Backspace удалить',DIM)
        elif kind=='unit-converter':
            names=['Байты → KiB / MiB / GiB','Метры → km / cm / ft','Celsius → Fahrenheit / Kelvin','Секунды → min / h / дни']
            box(f,2,4,width,max(4,h-8),'КОНВЕРТЕР · Tab режим')
            rows=[names[self.units],'› '+self.number+'▏']
            try:
                value=float(self.number)
                if not math.isfinite(value):raise ValueError()
                converted=[[(value/1024,'KiB'),(value/1024**2,'MiB'),(value/1024**3,'GiB')],[(value/1000,'km'),(value*100,'cm'),(value/.3048,'ft')],[(value*9/5+32,'°F'),(value+273.15,'K')],[(value/60,'min'),(value/3600,'h'),(value/86400,'дней')]][self.units]
                rows+=['%s %s'%(f'{number:.8g}',unit) for number,unit in converted]
            except ValueError:rows+=['Введите число']
            lines(rows)
        return f
