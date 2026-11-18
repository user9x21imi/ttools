"""Continuous light sculptures sampled onto the terminal's Braille subgrid."""
import math

class LightEffects:
    def _sculpture(self,f,t,p,kind):
        if kind=='chladni':
            points=[];cols=min(400,f.w*2);rows=min(320,f.h*4)
            dx=2/max(1,cols-1);dy=1.6/max(1,rows-1)
            for py in range(rows):
                y=(py/max(1,rows-1)-.5)*1.6
                for px in range(cols):
                    x=(px/max(1,cols-1)-.5)*2
                    val=math.cos(x*7+t*.08)*math.cos(y*11)-math.cos(x*11)*math.cos(y*7+t*.08)
                    gx=-7*math.sin(x*7+t*.08)*math.cos(y*11)+11*math.sin(x*11)*math.cos(y*7+t*.08)
                    gy=-11*math.cos(x*7+t*.08)*math.sin(y*11)+7*math.cos(x*11)*math.sin(y*7+t*.08)
                    if abs(val)<.48*math.hypot(gx*dx,gy*dy):points.append((px*f.w*2/cols,py*f.h*4/rows,p[min(4,py*5//rows)]))
            f.braille(points);return
        points=[];count=min(4800,max(800,f.w*f.h*2));ca,sa=math.cos(t*.13),math.sin(t*.13)
        for i in range(count):
            u=(i%240)/239;v=(i//240)/max(1,math.ceil(count/240)-1);a=u*math.tau
            if kind=='ribbons':
                x=(u-.5)*2.1;y=(v-.5)*.9+math.sin(u*8+t*.45+v*4)*.23;z=math.cos(u*8+t*.45+v*4)*.35
            elif kind=='gyroscope':
                ring=int(v*5);tilt=ring*.54+t*.16
                x=math.cos(a)*.8;y=math.sin(a)*math.cos(tilt)*.8;z=math.sin(a)*math.sin(tilt)*.8
            elif kind=='silk':
                x=(u-.5)*2;y=math.sin(u*6+v*2+t*.3)*.42+(v-.5)*.7;z=math.cos(u*9-v*3+t*.2)*.4
            elif kind=='bloom':
                r=.2+v*.7;angle=a+t*.12;y=(v-.5)*.8+math.sin(a*7+t*.4)*v*.18
                x=r*math.cos(angle);z=r*math.sin(angle)
            elif kind=='gyroid':
                x=(u-.5)*2;z=(v-.5)*2;y=(math.sin(x*4+t*.2)*math.cos(z*3)+math.sin(z*4)*math.cos(x*3+t*.2))*.27
            elif kind=='chladni':
                x=(u-.5)*2;y=(v-.5)*1.6;z=0
                val=math.cos(x*7+t*.08)*math.cos(y*11)-math.cos(x*11)*math.cos(y*7+t*.08)
                if abs(val)>.075:continue
            elif kind=='orbital_weave':
                phase=v*math.tau;x=math.cos(a)*(.55+.22*math.cos(phase*3+t*.3));z=math.sin(a)*(.55+.22*math.cos(phase*3+t*.3));y=math.sin(phase*3+a*2+t*.3)*.4
            else:
                r=.1+v*.8;x=r*math.cos(a);z=r*math.sin(a);y=math.sin(r*10-t*.8)*.3*(1-r)
            if kind!='chladni':x,z=x*ca+z*sa,z*ca-x*sa
            y,z=y*.88-z*.45,y*.45+z*.88
            perspective=3/max(1,3-z);sx=f.w+x*f.w*.75*perspective;sy=f.h*2+y*f.h*1.8*perspective
            points.append((sx,sy,p[min(4,int(v*4.99))]))
        f.braille(points)
    def light_ribbons(self,f,t,p):self._sculpture(f,t,p,'ribbons')
    def light_gyroscope(self,f,t,p):self._sculpture(f,t,p,'gyroscope')
    def light_silk(self,f,t,p):self._sculpture(f,t,p,'silk')
    def light_bloom(self,f,t,p):self._sculpture(f,t,p,'bloom')
    def light_gyroid(self,f,t,p):self._sculpture(f,t,p,'gyroid')
    def light_chladni(self,f,t,p):self._sculpture(f,t,p,'chladni')
    def light_orbits(self,f,t,p):self._sculpture(f,t,p,'orbital_weave')
    def light_resonance(self,f,t,p):self._sculpture(f,t,p,'resonance')
