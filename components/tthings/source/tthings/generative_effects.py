"""Original continuous generative scenes; no downloaded frames or dependencies."""
import math
import random

class GenerativeEffects:
    def _volume(self,f,t,p,kind):
        pts=[];n=min(6000,max(900,f.w*f.h*3));rot=t*.14;ca,sa=math.cos(rot),math.sin(rot)
        for i in range(n):
            u=(i%240)/239;v=(i//240)/max(1,math.ceil(n/240)-1);a=u*math.tau;b=v*math.tau
            if kind=='hopf':
                den=1.8-.65*math.sin(b);x=(1+.3*math.cos(b))*math.cos(a)/den;z=(1+.3*math.cos(b))*math.sin(a)/den;y=.65*math.sin(b+a)/den
            elif kind=='nautilus':
                a=u*math.tau*3;r=.08*math.exp(u*2.3);tube=r*.38
                x=(r+tube*math.cos(b))*math.cos(a);z=(r+tube*math.cos(b))*math.sin(a);y=tube*math.sin(b)+(u-.5)*.65
            elif kind=='heart':
                x=math.sin(a)**3*.8;y=-(13*math.cos(a)-5*math.cos(2*a)-2*math.cos(3*a)-math.cos(4*a))/20;z=(v-.5)*.28*math.sin(a)**2
                beat=1+.045*math.sin(t*3);x*=beat;y*=beat
            elif kind=='iris':
                r=.22+v*.64;angle=a+v*.7+math.sin(v*12+t*.4)*.09;x=r*math.cos(angle);y=r*math.sin(angle)*.8;z=math.sin(a*19+v*13+t*.3)*.1
            elif kind=='dunes':
                x=(u-.5)*2;z=(v-.5)*2;y=math.sin(x*4+math.sin(z*2+t*.13))* .18+math.cos(z*3-t*.2)*.18
            elif kind=='vessel':
                y=(v-.5)*1.5;r=.35+.15*math.sin(v*9+t*.25)+.15*v;x=r*math.cos(a);z=r*math.sin(a)
            elif kind=='helixnest':
                r=.55+.2*math.cos(b*3+t*.2);x=r*math.cos(a);z=r*math.sin(a);y=.26*math.sin(b*3+a*3+t*.2)
            else:
                angle=i*2.3999632297+t*.08;r=math.sqrt(i/n)*.85;x=r*math.cos(angle);z=r*math.sin(angle);y=.4*math.cos(r*5-t*.25)*(1-r)
            x,z=x*ca+z*sa,z*ca-x*sa;y,z=y*.9-z*.43,y*.43+z*.9;depth=3/max(1,3-z)
            pts.append((f.w+x*f.w*.75*depth,f.h*2+y*f.h*1.8*depth,p[min(4,int(v*4.99))]))
        f.braille(pts)
    def hopf_fibers(self,f,t,p):self._volume(f,t,p,'hopf')
    def nautilus_shell(self,f,t,p):self._volume(f,t,p,'nautilus')
    def luminous_heart(self,f,t,p):self._volume(f,t,p,'heart')
    def iris_filaments(self,f,t,p):self._volume(f,t,p,'iris')
    def dune_contours(self,f,t,p):self._volume(f,t,p,'dunes')
    def porcelain(self,f,t,p):self._volume(f,t,p,'vessel')
    def nested_helix(self,f,t,p):self._volume(f,t,p,'helixnest')
    def phyllotaxis(self,f,t,p):self._volume(f,t,p,'seeds')
    def fractal_flame(self,f,t,p):
        rng=random.Random(739);x,y=.1,.2;pts=[];count=min(16000,max(4000,f.w*f.h*6));angle=.45+.1*math.sin(t*.15)
        for i in range(count+30):
            branch=rng.randrange(17)
            if branch<7:
                xx=.72*x-.35*y+.28;yy=.35*x+.72*y
                x,y=math.sin(xx*1.6),math.sin(yy*1.6)
            elif branch<13:
                r=x*x+y*y+.1;x,y=(x*math.sin(r)-y*math.cos(r))*.62,(x*math.cos(r)+y*math.sin(r))*.62
            else:x,y=x*.5-.55,y*.5+.28
            if i>30:
                xx=x*math.cos(angle)-y*math.sin(angle);yy=x*math.sin(angle)+y*math.cos(angle)
                pts.append((f.w+xx*f.w*.68,f.h*2+yy*f.h*1.45,p[branch%5]))
        f.braille(pts)
    def water_caustics(self,f,t,p):
        chars=' ·:░▒▓';scale=max(1,f.h)
        for y in range(f.h):
            for x in range(f.w):
                u=x/scale*.55;v=y/scale
                a=math.sin(u*13+math.sin(v*11+t*.3)+t*.25);b=math.sin(v*15+math.cos(u*9-t*.23))
                glow=max(0,1-abs(a+b)*3)**3
                if glow>.04:
                    col=p[3] if glow<.5 else p[0];f.put(x,y,chars[min(5,int(glow*5)+1)],col)
