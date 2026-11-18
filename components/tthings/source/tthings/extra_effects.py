"""Additional original procedural scenes, inspired by classic terminal demos."""
import math
import random
from .rich_effects import RichEffects

from .light_effects import LightEffects

from .generative_effects import GenerativeEffects

from .gallery_effects import GalleryEffects

class ExtraEffects(RichEffects,LightEffects,GenerativeEffects,GalleryEffects):
    def aurora(self,f,t,p):
        for x in range(f.w):
            center=f.h*(.4+.14*math.sin(x*.06+t*.3)+.1*math.sin(x*.13-t*.2))
            for y in range(f.h):
                d=(y-center)/max(1,f.h*.28)
                if -.4<d<1:
                    v=max(0,1-abs(d))
                    f.put(x,y,'░▒▓'[min(2,int(v*2.99))],p[(int(x*.035+t*.2)+int(d*2))%5])
        for i in range(max(3,f.w//3)):f.put((i*23)%f.w,(i*7)%max(1,f.h//4),'·',p[3])

    def galaxy(self,f,t,p):
        points=[]
        for i in range(min(2200,f.w*f.h*3)):
            radius=(i/2200)**.6
            angle=i*2.39996+radius*8+t*.12
            angle=round(angle/math.tau*3)*math.tau/3+radius*8+t*.12+math.sin(i*71)*.18
            points.append((f.w+math.cos(angle)*radius*f.w*.94,f.h*2+math.sin(angle)*radius*f.h*1.4,p[(i//110)%5]))
        f.braille(points)

    def blackhole(self,f,t,p):
        points=[]
        for i in range(min(1800,f.w*f.h*3)):
            r=.16+((i*.618+t*.035)%1)*.8
            a=i*2.39996+t/(r+.1)
            x=math.cos(a)*r
            y=math.sin(a)*r*.25
            if y<0:y-=.11*math.exp(-x*x*12)
            points.append((f.w+x*f.w*.95,f.h*2+y*f.h*3,p[(i//90)%5]))
        f.braille(points)

    def ocean(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                v=math.sin(x*.18+y*.32-t*1.5)+.55*math.sin(x*.09-y*.41+t*.8)
                if v>.6:f.put(x,y,'~' if v>1.2 else '∿',p[0] if v>1 else p[3])
                elif v>0:f.put(x,y,'·',p[3])

    def ripple(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                r=math.hypot((x-f.w/2)*.5,y-f.h/2)
                v=math.sin(r*.9-t*3)
                if v>.2:f.put(x,y,'○' if v>.9 else '·',p[int(r/3)%5])

    def tunnel(self,f,t,p):
        for i in range(18):
            depth=((i+t*2)%18)/18
            radius=depth*depth
            w=max(1,radius*f.w*.5);h=max(1,radius*f.h*.5)
            cx=f.w/2+math.sin(t*.4+depth*3)*f.w*.1*(1-depth)
            cy=f.h/2+math.cos(t*.3+depth*3)*f.h*.1*(1-depth)
            f.line(cx-w,cy-h,cx+w,cy-h,'─',p[i%5]);f.line(cx-w,cy+h,cx+w,cy+h,'─',p[i%5])
            f.line(cx-w,cy-h,cx-w,cy+h,'│',p[i%5]);f.line(cx+w,cy-h,cx+w,cy+h,'│',p[i%5])

    def terrain(self,f,t,p):
        points=[]
        for row in range(1,24):
            depth=row/24
            for col in range(-40,41):
                wx=col*.2;wz=depth*9+t*.4
                height=math.sin(wx*.9+wz)*math.cos(wx*.5-wz*.7)+.4*math.sin(wx*2+wz*.6)
                points.append((f.w+wx/(depth+.2)*f.w*.12,f.h*3+depth*f.h-height*depth*f.h*.6,p[(row//5)%5]))
        f.braille(points)

    def dna(self,f,t,p):
        for y in range(f.h):
            a=y*.36+t
            cx=f.w/2;span=min(f.w*.35,f.h*.8)
            x1=cx+math.sin(a)*span;x2=cx-math.sin(a)*span
            if y%2==0:f.line(x1,y,x2,y,'─',p[4])
            f.text(int(x1),y,'●',p[0]);f.text(int(x2),y,'●',p[2])

    def lissajous(self,f,t,p):
        pts=[]
        for i in range(1500):
            a=i/1500*math.tau
            x=math.sin(a*3+t*.3)
            y=math.sin(a*(2+.1*math.sin(t*.1)))
            pts.append((f.w*(1+x*.9),f.h*2*(1+y*.9),p[(i//300)%5]))
        f.braille(pts)

    def lorenz(self,f,t,p):
        if 'trajectory' not in self.state:
            x,y,z=.1,.1,.1;points=[]
            for i in range(3500):
                x,y,z=x+10*(y-x)*.006,y+(x*(28-z)-y)*.006,z+(x*y-z*8/3)*.006
                if i>500:points.append((x,y,z))
            self.state['trajectory']=points
        pts=[];a=t*.12
        for i,(x,y,z) in enumerate(self.state['trajectory']):
            rx=x*math.cos(a)+y*math.sin(a)
            pts.append((f.w+rx*f.w*.039,f.h*3.7-z*f.h*.065,p[(i//600)%5]))
        f.braille(pts)

    def pendulum(self,f,t,p):
        for i in range(18):
            x=(i+.5)*f.w/18
            length=f.h*.68
            angle=math.sin(t*(.55+i*.025))*.8
            bx=x+math.sin(angle)*f.w*.05;by=f.h*.15+math.cos(angle)*length
            f.line(x,f.h*.12,bx,by,'·',p[i%5]);f.put(bx,by,'●',p[i%5])

    def kaleidoscope(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                dx=(x-f.w/2)*.5;dy=y-f.h/2
                r=math.hypot(dx,dy);a=math.atan2(dy,dx)
                v=math.sin(r*.4-t)+math.cos(a*8+t*.3)
                if v>.1:f.put(x,y,'░▒▓'[min(2,int(v*1.45))],p[int(r*.2+v*2+t*.3)%5])

    def lightning(self,f,t,p):
        rng=random.Random(int(t*2))
        for bolt in range(2):
            x=rng.uniform(.2,.8)*f.w;y=0
            while y<f.h:
                nx=x+rng.uniform(-f.w*.08,f.w*.08);ny=y+rng.uniform(1,4)
                f.line(x,y,nx,ny,'╱' if nx<x else '╲',p[3] if bolt else p[0])
                if rng.random()<.4:f.line(nx,ny,nx+rng.uniform(-8,8),ny+3,'·',p[3])
                x,y=nx,ny

    def bubbles(self,f,t,p):
        for i in range(max(5,f.w*f.h//100)):
            x=(i*17.7+math.sin(t*.5+i)*3)%f.w
            y=f.h-(i*7.3+t*(.8+i%4*.2))%f.h
            f.put(x,y,'○' if i%3 else '◯',p[i%5])

    def fireflies(self,f,t,p):
        for i in range(max(8,f.w*f.h//30)):
            brightness=math.sin(t*1.8+i*2)
            x=(i*13.3+math.sin(t*.23+i)*f.w*.12)%f.w
            y=(i*7.9+math.cos(t*.2+i)*f.h*.15)%f.h
            if brightness>-.2:f.put(x,y,'✦' if brightness>.85 else '·',p[i%5])

    def orbit(self,f,t,p):
        cx=f.w/2;cy=f.h/2;pts=[]
        for i in range(1,6):
            r=i*.15
            for j in range(90):
                a=j*math.tau/90
                pts.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2,p[3]))
            a=t/(i*.8)+i
            f.put(cx+math.cos(a)*r*f.w/2,cy+math.sin(a)*r*f.h/2,'●',p[i%5])
        # Draw paths first, then planets so paths never erase them.
        f.braille(pts)
        for i in range(1,6):
            a=t/(i*.8)+i;r=i*.15
            f.put(cx+math.cos(a)*r*f.w/2,cy+math.sin(a)*r*f.h/2,'●',p[i%5])
        f.put(cx,cy,'☀',p[4])

    def radar(self,f,t,p):
        pts=[];angle=t*.7
        for i in range(900):
            a=angle-(i%45)*.012;r=(i//45)/20
            pts.append((f.w+math.cos(a)*r*f.w*.85,f.h*2+math.sin(a)*r*f.h*1.7,p[0] if i%45<8 else p[1]))
        for i in range(180):
            a=i*math.tau/180
            pts.append((f.w+math.cos(a)*f.w*.85,f.h*2+math.sin(a)*f.h*1.7,p[3]))
        f.braille(pts)
        for i in range(8):
            a=i*2.39996;r=.2+(i*.137)% .7
            if (angle-a)%math.tau<1.7:f.put(f.w/2+math.cos(a)*r*f.w*.425,f.h/2+math.sin(a)*r*f.h*.85,'●',p[4])

    def boids(self,f,t,p):
        step=int(t*15)
        if 'flock' not in self.state:
            self.state['flock']=[[self.rng.random()*f.w,self.rng.random()*f.h,self.rng.uniform(-1,1),self.rng.uniform(-.5,.5)] for _ in range(36)]
        flock=self.state['flock']
        if self.last_step!=step:
            updated=[]
            for i,(x,y,vx,vy) in enumerate(flock):
                peers=[b for j,b in enumerate(flock) if i!=j and ((b[0]-x)*.5)**2+(b[1]-y)**2<64]
                if peers:
                    vx+=sum(b[2]-vx for b in peers)/len(peers)*.045
                    vy+=sum(b[3]-vy for b in peers)/len(peers)*.045
                    vx+=(sum(b[0] for b in peers)/len(peers)-x)*.0018
                    vy+=(sum(b[1] for b in peers)/len(peers)-y)*.0018
                    for ox,oy,_,_ in peers:
                        d=(ox-x)**2+(oy-y)**2
                        if d<9:vx-=(ox-x)*.025;vy-=(oy-y)*.025
                speed=max(.1,math.hypot(vx,vy*2));vx=vx/speed*.55;vy=vy/speed*.55
                updated.append([(x+vx)%f.w,(y+vy)%f.h,vx,vy])
            self.state['flock']=flock=updated;self.last_step=step
        for i,(x,y,vx,vy) in enumerate(flock):f.put(x,y,'›' if vx>0 else '‹',p[i%5])

    def maze(self,f,t,p):
        cols=max(1,(f.w-1)//2);rows=max(1,(f.h-1)//2)
        if 'maze' not in self.state:
            self.state.update(maze={(0,0)},stack=[(0,0)],links=[])
        visited=self.state['maze'];stack=self.state['stack']
        if int(t*12)!=self.last_step:
            for _ in range(3):
                if not stack:break
                x,y=stack[-1]
                choices=[(a,b) for a,b in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)] if 0<=a<cols and 0<=b<rows and (a,b) not in visited]
                if choices:
                    nx,ny=self.rng.choice(choices);visited.add((nx,ny));stack.append((nx,ny));self.state['links'].append((x,y,nx,ny))
                else:stack.pop()
            self.last_step=int(t*12)
        for y in range(f.h):
            for x in range(f.w):f.put(x,y,'░',p[3])
        for x,y in visited:f.put(x*2+1,y*2+1,' ',p[0])
        for x,y,nx,ny in self.state['links']:f.put(x+nx+1,y+ny+1,' ',p[0])
        if stack:f.put(stack[-1][0]*2+1,stack[-1][1]*2+1,'●',p[4])

    def fractal(self,f,t,p,julia=False):
        zoom=1.2+.2*math.sin(t*.2)
        for y in range(f.h):
            for x in range(f.w):
                z=complex((x/max(1,f.w-1)-.5)*3.5/zoom,(y/max(1,f.h-1)-.5)*2.5/zoom)
                c=complex(-.74+.06*math.sin(t*.1),.18+.06*math.cos(t*.15)) if julia else z-.45
                if not julia:z=0j
                n=0
                while abs(z)<2 and n<28:z=z*z+c;n+=1
                if n<28:f.put(x,y,' .░▒▓█'[min(5,n//3)],p[(n//2+int(t*.25))%5])

    def mandelbrot(self,f,t,p):self.fractal(f,t,p)
    def julia(self,f,t,p):self.fractal(f,t,p,True)

    def rings(self,f,t,p):
        points=[]
        for i in range(12):
            r=((i+t*.8)%12)/12
            for k in range(150):
                a=k*math.tau/150
                points.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2,p[i%5]))
        f.braille(points)

    def rose(self,f,t,p):
        points=[]
        for i in range(1800):
            a=i*math.tau/1800
            r=math.cos(5*a+t*.2)*.9
            points.append((f.w+math.cos(a+t*.1)*r*f.w,f.h*2+math.sin(a+t*.1)*r*f.h*2,p[(i//360)%5]))
        f.braille(points)

    def rainbows(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                r=math.hypot((x-f.w/2)*.5,y-f.h)
                if int(r-t*2)%8<3:f.put(x,y,'▒',p[int(r/3-t*.4)%5])
