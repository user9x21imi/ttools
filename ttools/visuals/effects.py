"""Original procedural renderers. No upstream projects are vendored."""
import colorsys
import datetime
import math
import random
from .extra_effects import ExtraEffects

PALETTES = [('#70e1ce', '#a9d89b', '#e7b7d3', '#92b9ec', '#f3c87a'),
            ('#9b8afb', '#cba6f7', '#f5c2e7', '#89b4fa', '#94e2d5'),
            ('#e7bc65', '#ee9365', '#d87979', '#e3d6a8', '#9ebc9a')]
BG = '#10151c'
DIM = '#526478'
FG = '#dbe5ee'

class Frame:
    def __init__(self, width, height):
        self.w, self.h = max(1, width), max(1, height)
        self.cells = [[(' ', FG) for _ in range(self.w)] for _ in range(self.h)]

    def put(self, x, y, char, color=FG):
        if not char.isprintable():char=' '
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = (char, color)

    def text(self, x, y, value, color=FG):
        for i, char in enumerate(value):
            self.put(x + i, y, char, color)

    def line(self, x0, y0, x1, y1, char='•', color=FG):
        n = max(abs(int(x1-x0)), abs(int(y1-y0)), 1)
        for i in range(n+1):
            self.put(x0+(x1-x0)*i/n, y0+(y1-y0)*i/n, char, color)

    def braille(self, points):
        grouped = {}
        dots = ((1, 8), (2, 16), (4, 32), (64, 128))
        for px, py, color in points:
            px, py = int(px), int(py)
            if 0 <= px < self.w*2 and 0 <= py < self.h*4:
                key = (px//2, py//4)
                bits, _ = grouped.get(key, (0, color))
                grouped[key] = (bits | dots[py%4][px%2], color)
        for (x,y), (bits,color) in grouped.items():
            self.put(x,y,chr(0x2800+bits),color)

    def plain(self):
        return '\n'.join(''.join(ch for ch,_ in row) for row in self.cells)

DIGITS = {
'0':['111','101','101','101','111'], '1':['010','110','010','010','111'],
'2':['111','001','111','100','111'], '3':['111','001','111','001','111'],
'4':['101','101','111','001','001'], '5':['111','100','111','001','111'],
'6':['111','100','111','101','111'], '7':['111','001','010','010','010'],
'8':['111','101','111','101','111'], '9':['111','101','111','001','111'],
':':['0','1','0','1','0']}

# Coarse hand-drawn polygons: deliberately not a geographic data product.
LAND = [ [(-168,65),(-140,71),(-115,70),(-82,53),(-53,48),(-65,25),(-87,14),(-105,26),(-125,47)],
[(-80,12),(-47,-2),(-35,-10),(-50,-35),(-70,-55),(-80,-10)],
[(-18,36),(15,38),(37,18),(51,10),(36,-25),(18,-35),(-5,5)],
[(-10,36),(-10,60),(35,70),(95,75),(170,58),(145,35),(110,5),(72,8),(40,35)],
[(112,-12),(150,-12),(155,-37),(130,-45),(113,-28)], [(-55,59),(-22,75),(-42,83),(-65,78)],
[(45,-13),(51,-16),(48,-25),(44,-23)]]

def inside(x,y,poly):
    result = False
    for (a,b),(c,d) in zip(poly, poly[1:]+poly[:1]):
        if (b>y) != (d>y) and x < (c-a)*(y-b)/(d-b)+a:
            result = not result
    return result

class Scene(ExtraEffects):
    def __init__(self, name, seed=None):
        self.name = name
        self.rng = random.Random(seed)
        self.size = None
        self.state = {}
        self.last_step = -1

    def render(self, w, h, t, palette=0):
        f = Frame(w,h)
        p = PALETTES[palette % len(PALETTES)]
        if self.size != (w,h):
            self.size = (w,h)
            self.state = {}
            self.last_step = -1
        getattr(self, self.name)(f,t,p)
        return f

    def lava(self,f,t,p):
        balls = [(math.sin(t*.25+i*2.1)*.65,math.cos(t*.19+i*1.7)*.65) for i in range(5)]
        pts=[]
        for y in range(f.h*4):
            ny=y/max(1,f.h*4-1)*2-1
            for x in range(f.w*2):
                nx=x/max(1,f.w*2-1)*2-1
                v=sum(.085/(.008+(nx-bx)**2+(ny-by)**2) for bx,by in balls)
                if v>1.0:
                    pts.append((x,y,p[min(4,int(v*1.2))]))
        f.braille(pts)

    def particles(self,f,t,p):
        points=[]
        for i in range(min(1300, f.w*f.h*2)):
            a=i*2.399963+t*.12
            radius=(i/1300)**.5
            for trail in range(3):
                phase=t*.3-trail*.025
                x=f.w*(1+radius*math.sin(a+math.sin(phase+radius*6)))*.99
                y=f.h*2*(1+radius*math.cos(a+math.cos(phase*.7+radius*4)))*.99
                points.append((x,y,p[(i//65)%5]))
        f.braille(points)

    def plasma(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                v=math.sin(x*.12+t)+math.sin(y*.22+t*.7)+math.sin(math.hypot(x*.1,y*.2)-t)
                rgb=colorsys.hsv_to_rgb((v*.13+t*.025)%1,.55,.85)
                f.put(x,y,'░▒▓█'[min(3,int((v+3)/6*3.99))], '#%02x%02x%02x'%tuple(int(c*255) for c in rgb))

    def fire(self,f,t,p):
        ramp=' .:░▒▓█'
        for y in range(f.h):
            level=y/f.h
            for x in range(f.w):
                v=level+.22*math.sin(x*.3+math.sin(t*2+x*.1)*2)+.12*math.sin(y*.8-t*5+x*.5)
                if v>.35:
                    col=['#70304c','#be4661','#ed855b','#ffd68b'][min(3,max(0,int(v*3)))]
                    f.put(x,y,ramp[min(6,max(0,int((v-.3)*8)))],col)

    def snow(self,f,t,p):
        for i in range(max(10,f.w*f.h//35)):
            speed=.8+(i%7)*.21
            x=(i*13.37+math.sin(t*.4+i)*2)%f.w
            y=(i*8.7+t*speed)%f.h
            f.put(x,y,'·' if i%3 else '*',p[i%5])

    def rain(self,f,t,p):
        for i in range(max(12,f.w*f.h//12)):
            x=(i*7.33-t*.8)%f.w
            y=(i*11.7+t*(6+i%4))%f.h
            f.put(x,y,'│' if i%4 else '╵',p[3] if i%3 else DIM)
        for i in range(max(1,f.w//10)):
            f.put((i*17+3)%f.w, f.h-1, '◡' if (int(t*3)+i)%2 else '·',p[3])

    def stars(self,f,t,p):
        points=[]
        for i in range(min(600,f.w*f.h//3)):
            a=i*2.39996
            z=1-((i*.017+t*.18)%1)
            radius=.025/max(.015,z)
            x=f.w+math.cos(a)*radius*f.w
            y=f.h*2+math.sin(a)*radius*f.h*2
            points.append((x,y,p[i%5] if z<.3 else DIM))
        f.braille(points)

    def matrix(self,f,t,p):
        chars='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZｱｲｳｴｵ'
        # ASCII avoids ambiguous-width halfwidth Katakana on older terminals.
        chars=chars[:36]
        for x in range(0,f.w,2):
            head=int(t*(4+x%7)+x*13)% (f.h+18)
            for j in range(16):
                y=head-j
                code=(x*7919+int(t*10)*17+j*997)%len(chars)
                f.put(x,y,chars[code], '#defbe9' if j==0 else ('#77de96' if j<5 else '#285f43'))

    def pipes(self,f,t,p):
        if 'grid' not in self.state:
            self.state['grid']=Frame(f.w,f.h)
            self.state['walkers']=[[self.rng.randrange(f.w),self.rng.randrange(f.h),self.rng.randrange(4),i] for i in range(5)]
        grid=self.state['grid']
        step=int(t*16)
        if step != self.last_step:
            for walker in self.state['walkers']:
                x,y,d,c=walker
                nd=(d+self.rng.choice([-1,0,0,0,1]))%4
                connections={ (0,0):'│',(2,2):'│',(1,1):'─',(3,3):'─',
                (0,1):'┌',(0,3):'┐',(1,0):'┘',(1,2):'┐',
                (2,1):'└',(2,3):'┘',(3,0):'└',(3,2):'┌'}
                grid.put(x,y,connections.get((d,nd),'┼'),p[c])
                dx,dy=[(0,-1),(1,0),(0,1),(-1,0)][nd]
                walker[:3]=[(x+dx)%f.w,(y+dy)%f.h,nd]
            self.last_step=step
        f.cells=[row[:] for row in grid.cells]

    def life(self,f,t,p):
        if 'cells' not in self.state:
            self.state['cells']={(x,y) for y in range(f.h) for x in range(f.w) if self.rng.random()<.25}
        step=int(t*7)
        cells=self.state['cells']
        if step!=self.last_step:
            counts={}
            for x,y in cells:
                for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
                    key=((x+dx)%f.w,(y+dy)%f.h)
                    counts[key]=counts.get(key,0)+1
            cells={cell for cell,n in counts.items() if n==3 or (n==2 and cell in cells)}
            self.state['cells']=cells
            self.last_step=step
        for x,y in cells:
            f.put(x,y,'▪',p[(x//12+y//6)%5])

    def tree(self,f,t,p,sakura=False):
        rng=random.Random(81)
        branches=[]
        def branch(x,y,length,angle,depth):
            if depth<=0 or length<.45:
                return
            ex=x+math.cos(angle)*length*1.65
            ey=y+math.sin(angle)*length*.75
            branches.append((x,y,ex,ey,depth))
            branch(ex,ey,length*rng.uniform(.62,.78),angle-rng.uniform(.3,.7),depth-1)
            branch(ex,ey,length*rng.uniform(.62,.78),angle+rng.uniform(.3,.7),depth-1)
        branch(f.w*.5,f.h*.83,max(1,min(f.h*.30,f.w*.19)),-math.pi/2,8)
        progress=min(1,(t+1)/12)
        for x,y,ex,ey,depth in branches:
            if (8-depth)/8>progress:
                continue
            f.line(x,y,ex,ey,'│' if depth>4 else ('*' if sakura else '♣'), '#a88c73' if depth>4 else (p[2] if sakura else p[1]))
        f.text(f.w//2-5,int(f.h*.85),'╰────────╯',p[4])
        f.text(f.w//2-3,int(f.h*.85)+1,'╲____╱',p[4])
        if sakura:
            for i in range(max(4,f.w//4)):
                f.put((i*13.1+math.sin(t+i)*3)%f.w,(i*3.7+t*1.1)%f.h,'·',p[2])

    def bonsai(self,f,t,p): self.tree(f,t,p)
    def sakura(self,f,t,p): self.tree(f,t,p,True)

    def aquarium(self,f,t,p):
        for x in range(f.w):
            f.put(x,f.h-1,'~' if x%3 else '·',p[4])
        for i in range(max(2,f.w//12)):
            x=(i*19+5)%f.w
            for j in range(max(1,f.h//3)):
                f.put(x+math.sin(t+i+j*.8),f.h-2-j,'(' if j%2 else ')',p[1])
        for i in range(max(3,f.w//15)):
            right=i%2==0
            fish='><(((°>' if right else '<°)))><'
            x=(i*23+t*(2+i%3)*(1 if right else -1))%(f.w+10)-8
            y=1+(i*7)%max(1,f.h-5)
            f.text(int(x),y,fish,p[i%5])
        for i in range(max(3,f.w//10)):
            f.put((i*17+9)%f.w,f.h-2-(t*2+i*4)%max(1,f.h-2),'o' if i%2 else '°',p[3])

    def fireworks(self,f,t,p):
        points=[]
        for i in range(5):
            age=(t+i*.83)%4
            cx=f.w*(.15+(i*.237)% .7)*2
            cy=f.h*(.2+(i*.173)% .35)*4
            if age<.8:
                points.append((cx, f.h*4-(f.h*4-cy)*age/.8,p[i]))
            else:
                age-=.8
                for k in range(70):
                    a=k*2.39996
                    speed=3+(k%11)*.65
                    points.append((cx+math.cos(a)*speed*age,cy+math.sin(a)*speed*age+age*age*4,p[i] if age<2 else DIM))
        f.braille(points)

    def globe(self,f,t,p):
        r=max(.5,min(f.w/2.2,f.h*.88))
        for y in range(f.h):
            for x in range(f.w):
                nx=(x-f.w/2)/r
                ny=-(y-f.h/2)*2/r
                d=nx*nx+ny*ny
                if d>1: continue
                z=math.sqrt(1-d)
                lat=math.degrees(math.asin(ny))
                lon=(math.degrees(math.atan2(nx,z))+t*9+180)%360-180
                land=any(inside(lon,lat,poly) for poly in LAND)
                f.put(x,y,'▓' if land else ('·' if int(lat)%15<2 or int(lon)%20<2 else ' '),p[1] if land else p[3])

    def clock(self,f,t,p):
        now=datetime.datetime.now()
        text=now.strftime('%H:%M:%S')
        units=sum(len(DIGITS[c][0])+1 for c in text)-1
        sx=max(1,min(3,f.w//max(1,units)))
        if units>f.w or f.h<7:
            f.text(max(0,(f.w-len(text))//2),f.h//2,text,p[0]); return
        x=(f.w-units*sx)//2
        y=max(0,(f.h-7)//2)
        for c in text:
            pattern=DIGITS[c]
            for py,row in enumerate(pattern):
                for px,v in enumerate(row):
                    if v=='1': f.text(x+px*sx,y+py,'█'*sx,p[0])
            x+=(len(pattern[0])+1)*sx
        date=now.strftime('%d.%m.%Y')
        f.text((f.w-len(date))//2,y+6,date,DIM)

    def donut(self,f,t,p):
        depth={}
        a,b=t*.7,t*.4
        for i in range(85):
            u=i*math.tau/85
            for j in range(32):
                v=j*math.tau/32
                x=(2+math.cos(v))*math.cos(u)
                y=(2+math.cos(v))*math.sin(u)
                z=math.sin(v)
                y,z=y*math.cos(a)-z*math.sin(a),y*math.sin(a)+z*math.cos(a)
                x,y=x*math.cos(b)-y*math.sin(b),x*math.sin(b)+y*math.cos(b)
                scale=min(f.w/8,f.h/4)
                px,py=int(f.w/2+x*scale),int(f.h/2+y*scale*.5)
                if z>depth.get((px,py),-99):
                    depth[(px,py)]=z
                    f.put(px,py,'.:-=+*#%@'[min(8,max(0,int((z+3)/6*8)))],p[min(4,max(0,int((z+3)/6*4)))])

    def dvd(self,f,t,p):
        text='[ TTHINGS ]'
        def bounce(v,limit):
            if limit<=0:return 0
            q=v%(2*limit)
            return q if q<limit else 2*limit-q
        f.text(bounce(t*7,f.w-len(text)),bounce(t*2.8,f.h-1),text,p[int(t/3)%5])

    def spectrum(self,f,t,p):
        for x in range(0,f.w,3):
            n=int((.15+.75*abs(math.sin(t*2+x*.14)*math.cos(t*.7+x*.04)))*f.h)
            for y in range(n):
                f.text(x,f.h-1-y,'██',p[min(4,int(y/max(1,f.h)*5))])
