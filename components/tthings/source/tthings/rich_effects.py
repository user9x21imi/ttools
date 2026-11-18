"""A larger collection of original generative scenes, all self-contained."""
import math
import random

TAU=math.tau

class RichEffects:
    def _project(self,f,points,t,p,scale=1):
        result=[];a=t*.22;b=.3*math.sin(t*.17);ca,sa=math.cos(a),math.sin(a);cb,sb=math.cos(b),math.sin(b)
        for i,point in enumerate(points):
            x,y,z=point[:3];x,z=x*ca+z*sa,z*ca-x*sa;y,z=y*cb-z*sb,y*sb+z*cb
            perspective=3.5/max(.5,3.5-z)
            result.append((f.w+x*f.w*.62*scale*perspective,f.h*2+y*f.h*1.5*scale*perspective,p[(i//50)%5]))
        f.braille(result)

    def nebula(self,f,t,p):
        pts=[]
        for i in range(min(2400,f.w*f.h*3)):
            u=i*2.39996;r=(i/2400)**.55
            a=u+math.sin(r*5+t*.12)*2
            pts.append((f.w+math.cos(a)*r*f.w*.92, f.h*2+math.sin(a)*r*f.h*1.5+math.sin(a*3+t*.2)*f.h*.2,p[(i//160+int(t*.1))%5]))
        f.braille(pts)

    def pulsar(self,f,t,p):
        pts=[]
        for i in range(1200):
            u=i/1200*TAU;r=.15+.025*math.sin(i*1.7+t*4)
            pts.append((f.w+math.cos(u)*r*f.w,f.h*2+math.sin(u)*r*f.h*2,p[4]))
        a=t*.9
        for side in (-1,1):
            for i in range(450):
                r=i/450*.9;spread=math.sin(i*19.1)*r*.09
                pts.append((f.w+side*(math.cos(a)*r+spread)*f.w,f.h*2+side*math.sin(a)*r*f.h*2,p[i//90%5]))
        f.braille(pts)

    def comet(self,f,t,p):
        pts=[];cx=f.w*(1+math.sin(t*.23)*.65);cy=f.h*2*(1+math.cos(t*.19)*.6)
        for i in range(1000):
            age=(i/1000)**1.4
            x=cx-age*f.w*.9;y=cy+math.sin(i*2.4)*age*f.h*.5
            pts.append((x,y,p[4] if age<.1 else p[int(age*5)%5]))
        f.braille(pts)

    def meteors(self,f,t,p):
        pts=[]
        for i in range(40):
            phase=(t*.25+i*.197)%1
            for j in range(12):
                x=((i*.618)%1-phase)*f.w*3+j*1.2;y=(phase*1.7+(i*.31)%1)*f.h*4-j*1.4
                pts.append((x,y,p[i%5] if j<3 else '#536779'))
        f.braille(pts)

    def saturn(self,f,t,p):
        pts=[]
        for i in range(2200):
            a=i*2.39996
            if i<1300:
                z=1-2*i/1300;r=math.sqrt(max(0,1-z*z));x=math.cos(a)*r*.48;y=math.sin(a)*r*.48
                pts.append((f.w+x*f.w,f.h*2+z*f.h*.95,p[min(4,int((y+.5)*5))]))
            else:
                r=.67+.25*((i*.618+t*.015)%1)
                x=math.cos(a)*r;y=math.sin(a)*r*.3
                if y>0 or abs(x)>.48:pts.append((f.w+x*f.w,f.h*2+y*f.h*2,p[4] if i%3 else p[2]))
        f.braille(pts)

    def wormhole(self,f,t,p):
        pts=[]
        for ring in range(35):
            z=((ring+t*3)%35)/35;r=(.03+z*z)*.95
            cx=math.sin(z*4+t*.3)*(1-z)*.35;cy=math.cos(z*3+t*.2)*(1-z)*.3
            for k in range(80):
                a=k*TAU/80+z*3+t*.12
                pts.append((f.w*(1+cx+math.cos(a)*r),f.h*2*(1+cy+math.sin(a)*r),p[ring%5]))
        f.braille(pts)

    def startrails(self,f,t,p):
        pts=[]
        for i in range(170):
            r=(i*.618%1)**.5;a=i*2.4+t*.04
            for j in range(16):
                b=a-j*.006
                pts.append((f.w+math.cos(b)*r*f.w,f.h*2+math.sin(b)*r*f.h*2,p[i%5]))
        f.braille(pts)

    def moon(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                nx=(x-f.w/2)/max(1,min(f.w*.42,f.h*.9));ny=(y-f.h/2)*2/max(1,min(f.w*.42,f.h*.9));d=nx*nx+ny*ny
                if d<1:
                    z=math.sqrt(1-d);light=nx*math.sin(t*.1)+z*math.cos(t*.1)
                    texture=math.sin(nx*31+ny*13)*math.sin(ny*27-nx*8)
                    if light>0:f.put(x,y,'░▒▓█'[min(3,max(0,int((light*.8+texture*.12)*4)))],p[4])

    def eclipse(self,f,t,p):
        radius=max(1,min(f.w*.32,f.h*.7));shift=math.sin(t*.17)*radius*1.7
        for y in range(f.h):
            for x in range(f.w):
                dx=x-f.w/2;dy=(y-f.h/2)*2;r=math.hypot(dx,dy)
                if radius*.93<r<radius*1.4 and math.hypot(dx-shift,dy)>radius:
                    f.put(x,y,'▓' if r<radius*1.05 else '·',p[4] if r<radius*1.12 else p[2])

    def supernova(self,f,t,p):
        pts=[];phase=(t*.16)%1
        for i in range(2200):
            a=i*2.39996;r=phase*(.2+.8*((i*.618)%1));jitter=math.sin(i*71)*.04
            pts.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2+jitter*f.h,p[(i//200+int(phase*4))%5]))
        f.braille(pts)

    def clouds(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                v=math.sin(x*.07-t*.15)+math.sin(y*.16+x*.03+t*.1)+.5*math.sin(x*.18+y*.09-t*.24)
                if v>.3:f.put(x,y,'░▒▓'[min(2,int((v-.3)*1.3))],p[3] if v<1.5 else p[0])

    def waterfall(self,f,t,p):
        for x in range(f.w):
            center=abs(x-f.w/2)/max(1,f.w*.3)
            if center>1:continue
            for y in range(f.h):
                phase=(y*.7-t*7+math.sin(x*.7)*2)%5
                if phase<3:f.put(x,y,'│' if phase<1 else '╎',p[0] if center<.4 else p[3])
        for i in range(80):f.put((i*17.3+t*2)%f.w,f.h-1-(i%4)*abs(math.sin(t+i)), '·',p[3])

    def autumn(self,f,t,p):
        colors=['#d28b43','#e5b657','#bf6b54','#e3a981','#a69b5b']
        for i in range(max(15,f.w*f.h//30)):
            x=(i*17.3+math.sin(t*.4+i)*f.w*.15)%f.w;y=(i*9.7+t*(.6+i%3*.2))%f.h
            f.put(x,y,['❧','·','*','~'][int(t*.6+i)%4],colors[i%5])

    def meadow(self,f,t,p):
        for x in range(0,f.w,2):
            h=2+(x*17)%max(3,f.h//3)
            for j in range(h):f.put(x+math.sin(t+x*.2+j*.1),f.h-1-j,'╱' if j%2 else '│',p[1])
            f.put(x+math.sin(t+x*.2+h*.1),f.h-h-1,'*' if x%3 else '✿',p[(x//2)%5])
        for i in range(8):f.put((i*19+t*1.4)%f.w,(i*7)%max(1,f.h//2),'·',p[4])

    def forest(self,f,t,p):
        for i in range(max(4,f.w//8)):
            x=(i*17)%f.w;h=3+(i*7)%max(4,f.h-3);base=f.h-2
            for y in range(h):
                half=(h-y)*.55;sway=math.sin(t*.3+i)*y*.04
                for dx in range(-int(half),int(half)+1):f.put(x+dx+sway,base-y,'▲' if y%3==0 else '░',p[1] if i%2 else p[0])
            f.put(x,base+1,'│',p[4])

    def rainwindow(self,f,t,p):
        for i in range(max(10,f.w//2)):
            x=(i*13)%f.w;head=(i*7.3+t*(1+i%3))%f.h
            for j in range(5):f.put(x,head-j,'│' if j<3 else '·',p[3] if j<2 else '#536779')
        f.line(f.w//2,0,f.w//2,f.h-1,'│',p[4]);f.line(0,f.h//2,f.w-1,f.h//2,'─',p[4])

    def campfire(self,f,t,p):
        for i in range(35):f.put((i*31)%f.w,(i*7)%max(1,f.h//2),'·',p[3])
        for x in range(max(0,f.w//2-8),min(f.w,f.w//2+8)):f.put(x,f.h-2,'═' if x%3 else '╳',p[4])
        for y in range(max(1,f.h//2)):
            half=max(0,(f.h*.45-y)*.35+math.sin(t*3+y)*1.5)
            for x in range(-int(half),int(half)+1):f.put(f.w//2+x,f.h-3-y,'▓' if y<3 else '░',['#e9bb62','#dc8e53','#c26b64'][y%3])

    def jellyfish(self,f,t,p):
        pts=[]
        for i in range(5):
            cx=f.w*(.2+(i*.193)% .7);cy=f.h*(1.2+math.sin(t*.3+i)*.5)
            for k in range(150):
                a=k/150*math.pi;r=1+.08*math.sin(t*2+i)
                pts.append((cx+math.cos(a)*f.w*.09*r,cy-math.sin(a)*f.h*.3*r,p[i]))
            for tentacle in range(5):
                for k in range(50):
                    y=k/50
                    pts.append((cx+(tentacle-2)*f.w*.025+math.sin(t*1.5+y*5+tentacle)*y*f.w*.02,cy+y*f.h*.9,p[i]))
        f.braille(pts)

    def butterflies(self,f,t,p):
        pts=[]
        for i in range(8):
            cx=(i*.23+t*.012)%1*2*f.w;cy=(.5+.35*math.sin(t*.23+i))*f.h*4
            flap=.3+.7*abs(math.sin(t*3+i))
            for k in range(100):
                a=k*TAU/100;r=math.sin(a*2)**2
                pts.append((cx+math.cos(a)*r*f.w*.07*flap,cy+math.sin(a)*r*f.h*.18,p[i%5]))
        f.braille(pts)

    def flowers(self,f,t,p):
        pts=[]
        for i in range(7):
            cx=(.15+(i*.257)% .7)*f.w*2;cy=(.2+(i*.193)% .6)*f.h*4
            for k in range(230):
                a=k*TAU/230;r=abs(math.sin(a*(3+i%4)))*(.8+.2*math.sin(t*.5+i))
                pts.append((cx+math.cos(a+t*.07)*r*f.w*.13,cy+math.sin(a+t*.07)*r*f.h*.3,p[i%5]))
        f.braille(pts)

    def coral(self,f,t,p):
        rng=random.Random(39)
        def grow(x,y,length,a,depth):
            if depth<1:return
            nx=x+math.cos(a)*length*1.6;ny=y+math.sin(a)*length
            f.line(x,y,nx,ny,'·',p[depth%5])
            sway=.06*math.sin(t*.5+depth)
            grow(nx,ny,length*.69,a-.42+sway,depth-1);grow(nx,ny,length*.72,a+.4+sway,depth-1)
        for i in range(5):grow((i+1)*f.w/6,f.h-1,max(1,f.h*.22),-math.pi/2,8)

    def sand(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                h=f.h*(.55+.12*math.sin(x*.06+t*.08)+.08*math.sin(x*.12-t*.04))
                if y>h:f.put(x,y,'·' if (x+y)%3 else '░',p[4] if y-h<3 else '#b39c72')
        for i in range(160):f.put((i*13.1+t*(1+i%4))%f.w,(i*7.7+math.sin(t+i))%f.h,'·',p[4])

    def fountain(self,f,t,p):
        pts=[]
        for i in range(1400):
            age=(t*.3+i*.618)%1;speed=.8+(i%11)*.035;vx=math.sin(i*2.4)*.5
            pts.append((f.w+vx*age*f.w,f.h*3.7-speed*age*(1-age)*f.h*13,p[i//280%5]))
        f.braille(pts)

    def sparks(self,f,t,p):
        pts=[]
        for i in range(650):
            age=(t*.7+i*.618)%1;a=i*2.4
            pts.append((f.w+math.cos(a)*age*f.w*.65,f.h*3-math.sin(a)*age*f.h*2+age*age*f.h,p[4] if age<.4 else p[2]))
        f.braille(pts)

    def magnets(self,f,t,p):
        pts=[]
        a1=(math.sin(t*.3)*.6,math.cos(t*.2)*.4);a2=(-a1[0],-a1[1])
        for i in range(90):
            x=math.cos(i*TAU/90)*.05+a1[0];y=math.sin(i*TAU/90)*.05+a1[1]
            for k in range(30):
                dx1=x-a1[0];dy1=y-a1[1];dx2=x-a2[0];dy2=y-a2[1]
                d1=(dx1*dx1+dy1*dy1+.01)**1.5;d2=(dx2*dx2+dy2*dy2+.01)**1.5
                vx=dx1/d1-dx2/d2;vy=dy1/d1-dy2/d2;norm=max(.01,math.hypot(vx,vy))
                x+=vx/norm*.04;y+=vy/norm*.04;pts.append((f.w*(1+x),f.h*2*(1+y),p[i//18%5]))
        f.braille(pts)

    def vortex(self,f,t,p):
        pts=[]
        for i in range(2000):
            r=(1-(i*.618+t*.04)%1)**.7;a=i*2.39996+t/(r+.12)
            pts.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2,p[i//200%5]))
        f.braille(pts)

    def fluid(self,f,t,p):
        pts=[]
        for i in range(min(1600,f.w*f.h*2)):
            x=(i*.618)%1*2-1;y=(i*.414)%1*2-1
            for j in range(4):
                phase=t*.2-j*.02
                x+=.1*math.sin(y*4+phase);y+=.1*math.cos(x*4-phase)
            pts.append((f.w*(1+x*.8),f.h*2*(1+y*.8),p[i//160%5]))
        f.braille(pts)

    def smoke(self,f,t,p):
        pts=[]
        for i in range(1800):
            age=(t*.12+i*.618)%1;spread=.03+age*.28
            x=math.sin(age*8-t*.6)*age*.3+math.sin(i*2.4)*spread
            pts.append((f.w*(1+x),f.h*4*(1-age),p[3] if i%3 else '#536779'))
        f.braille(pts)

    def diffusion(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                v=math.sin(x*.22+math.sin(y*.17+t*.12)*3)+math.cos(y*.33-math.cos(x*.14-t*.09)*3)
                if abs(v)<.32:f.put(x,y,'▓' if abs(v)<.12 else '░',p[(int(x/14)+int(y/7))%5])

    def explosion(self,f,t,p):
        pts=[];age=t%5
        for i in range(2000):
            a=i*2.39996;speed=(i*.618)%1
            r=math.log1p(age*3)*speed*.5
            pts.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2,p[(i//200+int(age))%5]))
        f.braille(pts)

    def cube(self,f,t,p):
        vertices=[(x,y,z) for x in (-.7,.7) for y in (-.7,.7) for z in (-.7,.7)];points=[]
        for i,a in enumerate(vertices):
            for b in vertices[i+1:]:
                if sum(x!=y for x,y in zip(a,b))==1:
                    for k in range(65):points.append(tuple(x+(y-x)*k/64 for x,y in zip(a,b)))
        self._project(f,points,t,p)

    def tesseract(self,f,t,p):
        vertices=[(x,y,z,w) for x in (-.5,.5) for y in (-.5,.5) for z in (-.5,.5) for w in (-.5,.5)];projected=[]
        for x,y,z,w in vertices:
            x,w=x*math.cos(t*.3)-w*math.sin(t*.3),x*math.sin(t*.3)+w*math.cos(t*.3)
            scale=1.6/(1.6-w);projected.append((x*scale,y*scale,z*scale))
        points=[]
        for i,a in enumerate(vertices):
            for j,b in enumerate(vertices[i+1:],i+1):
                if sum(x!=y for x,y in zip(a,b))==1:
                    for k in range(35):points.append(tuple(x+(y-x)*k/34 for x,y in zip(projected[i],projected[j])))
        self._project(f,points,t,p)

    def sphere(self,f,t,p):
        points=[]
        for lat in range(1,16):
            b=lat*math.pi/16
            for k in range(100):
                a=k*TAU/100;points.append((math.sin(b)*math.cos(a)*.85,math.cos(b)*.85,math.sin(b)*math.sin(a)*.85))
        for lon in range(16):
            a=lon*TAU/16
            for k in range(60):
                b=k*math.pi/59;points.append((math.sin(b)*math.cos(a)*.85,math.cos(b)*.85,math.sin(b)*math.sin(a)*.85))
        self._project(f,points,t,p)

    def torusknot(self,f,t,p):
        points=[]
        for i in range(2400):
            a=i*TAU/2400;r=.55+.22*math.cos(3*a)
            points.append((r*math.cos(2*a),r*math.sin(2*a),.3*math.sin(3*a)))
        self._project(f,points,t,p)

    def mobius(self,f,t,p):
        points=[]
        for i in range(220):
            a=i*TAU/220
            for j in range(12):
                v=(j/11-.5)*.5;r=.6+v*math.cos(a/2)
                points.append((r*math.cos(a),r*math.sin(a),v*math.sin(a/2)))
        self._project(f,points,t,p)

    def klein(self,f,t,p):
        points=[]
        for i in range(160):
            u=i*TAU/160
            for j in range(20):
                v=j*TAU/20;r=2+math.cos(u/2)*math.sin(v)-math.sin(u/2)*math.sin(2*v)
                points.append((r*math.cos(u)*.24,r*math.sin(u)*.24,(math.sin(u/2)*math.sin(v)+math.cos(u/2)*math.sin(2*v))*.3))
        self._project(f,points,t,p)

    def helix(self,f,t,p):
        points=[]
        for i in range(1900):
            a=i/1900*TAU*5;points.append((math.cos(a)*.5,(i/1900-.5)*1.8,math.sin(a)*.5))
        self._project(f,points,t,p)

    def superformula(self,f,t,p):
        points=[];m=5+2*math.sin(t*.1)
        for i in range(2200):
            a=i*TAU/2200
            r=(abs(math.cos(m*a/4))**1.5+abs(math.sin(m*a/4))**1.5)**(-1/.5)*.75
            points.append((f.w+math.cos(a)*r*f.w,f.h*2+math.sin(a)*r*f.h*2,p[i//440%5]))
        f.braille(points)

    def harmonograph(self,f,t,p):
        pts=[]
        for i in range(2200):
            u=i/2200*20;d=math.exp(-u*.04)
            x=(math.sin(u*2.01+t*.1)+math.sin(u*3.03))*.45*d
            y=(math.sin(u*2.03)+math.sin(u*3.01+t*.15))*.45*d
            pts.append((f.w*(1+x),f.h*2*(1+y),p[i//440%5]))
        f.braille(pts)

    def spirograph(self,f,t,p):
        pts=[];R=.75;r=.27;d=.48
        for i in range(2600):
            a=i/2600*TAU*12
            x=(R-r)*math.cos(a)+d*math.cos((R-r)/r*a+t*.1)
            y=(R-r)*math.sin(a)-d*math.sin((R-r)/r*a+t*.1)
            pts.append((f.w*(1+x*.9),f.h*2*(1+y*.9),p[i//520%5]))
        f.braille(pts)

    def moire(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                a=math.hypot((x-f.w*.4)*.5,y-f.h*.5);b=math.hypot((x-f.w*(.6+.1*math.sin(t*.2)))*.5,y-f.h*.5)
                if (int(a*.9)+int(b*.9))%2:f.put(x,y,'▒',p[(int(a/4)+int(t*.2))%5])

    def interference(self,f,t,p):
        sources=[(f.w*(.5+.3*math.sin(t*.13+i*2)),f.h*(.5+.3*math.cos(t*.11+i*2))) for i in range(3)]
        for y in range(f.h):
            for x in range(f.w):
                v=sum(math.sin(math.hypot((x-a)*.5,y-b)*.65-t) for a,b in sources)
                if v>.3:f.put(x,y,'░▒▓█'[min(3,int(v*1.3))],p[int(v*2)%5])

    def checkerboard(self,f,t,p):
        for y in range(f.h):
            depth=(y+1)/f.h
            for x in range(f.w):
                xx=(x-f.w/2)/max(.05,depth)*.08;zz=1/depth+t*.6
                if (int(math.floor(xx))+int(math.floor(zz)))%2:f.put(x,y,'▓',p[int(zz)%5])

    def waves3d(self,f,t,p):
        points=[]
        for i in range(55):
            x=(i/54-.5)*1.7
            for j in range(40):
                z=(j/39-.5)*1.7;y=math.sin(x*5+z*4-t)*.22+math.cos(z*4-x*3+t*.7)*.13
                points.append((x,y,z))
        self._project(f,points,t,p)

    def quasicrystal(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                v=sum(math.cos((x*.1*math.cos(i*math.pi/5)+y*.2*math.sin(i*math.pi/5))+t*.3) for i in range(5))
                n=int(abs(v)*2)
                if n%3:f.put(x,y,'░▒▓'[n%3],p[n%5])

    def vectorgrid(self,f,t,p):
        for y in range(1,f.h,3):
            for x in range(2,f.w,5):
                a=math.atan2(y-f.h/2,(x-f.w/2)*.5)+t*.25
                dx=math.cos(a)*2;dy=math.sin(a)
                f.line(x-dx,y-dy,x+dx,y+dy,'·',p[(x//5+y//3)%5]);f.put(x+dx,y+dy,'›' if dx>0 else '‹',p[0])

    def sierpinski(self,f,t,p):
        vertices=[(f.w,f.h*.15),(f.w*.1,f.h*3.7),(f.w*1.9,f.h*3.7)]
        rng=random.Random(17);x,y=f.w,f.h*2;pts=[]
        for i in range(5500):
            vx,vy=vertices[rng.randrange(3)];x=(x+vx)/2;y=(y+vy)/2
            if i>10:pts.append((x,y,p[(i//1100+int(t*.2))%5]))
        f.braille(pts)

    def fern(self,f,t,p):
        rng=random.Random(9);x=y=0.;pts=[];sway=math.sin(t*.25)*.08
        for i in range(6000):
            r=rng.random()
            if r<.01:x,y=0,.16*y
            elif r<.86:x,y=.85*x+.04*y,-.04*x+.85*y+1.6
            elif r<.93:x,y=.2*x-.26*y,.23*x+.22*y+1.6
            else:x,y=-.15*x+.28*y,.26*x+.24*y+.44
            pts.append((f.w+(x+sway*y)*f.w*.28,f.h*3.9-y*f.h*.37,p[1] if i%3 else p[0]))
        f.braille(pts)

    def dragon(self,f,t,p):
        sequence=[1]
        for _ in range(11):sequence=sequence+[1]+[-v for v in reversed(sequence)]
        x=y=0.;a=0.;points=[(x,y)]
        for turn in sequence:a+=turn*math.pi/2;x+=math.cos(a);y+=math.sin(a);points.append((x,y))
        lo=min(x for x,y in points);hi=max(x for x,y in points);top=min(y for x,y in points);bottom=max(y for x,y in points)
        f.braille([((x-lo)/max(1,hi-lo)*(f.w*2-2),(y-top)/max(1,bottom-top)*(f.h*4-2),p[(i//450+int(t*.2))%5]) for i,(x,y) in enumerate(points)])

    def hilbert(self,f,t,p):
        points=[];n=64
        for d in range(n*n):
            x=y=0;s=1;value=d
            while s<n:
                rx=1&(value//2);ry=1&(value^rx)
                if ry==0:
                    if rx==1:x=s-1-x;y=s-1-y
                    x,y=y,x
                x+=s*rx;y+=s*ry;value//=4;s*=2
            if d<int((.3+.7*((t*.04)%1))*n*n):points.append((x/max(1,n-1)*(f.w*2-2),y/max(1,n-1)*(f.h*4-2),p[(d//820)%5]))
        f.braille(points)

    def koch(self,f,t,p):
        points=[complex(0,-1),complex(.866,.5),complex(-.866,.5),complex(0,-1)]
        for _ in range(4):
            out=[]
            for a,b in zip(points,points[1:]):
                d=(b-a)/3;out.extend([a,a+d,a+d+d*complex(.5,-math.sqrt(3)/2),a+2*d])
            points=out+[points[-1]]
        angle=t*.07;rot=complex(math.cos(angle),math.sin(angle));pts=[]
        for i,z in enumerate(points):z*=rot;pts.append((f.w+z.real*f.w*.8,f.h*2+z.imag*f.h*1.6,p[i//160%5]))
        f.braille(pts)

    def burningship(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                c=complex(-1.76+(x/max(1,f.w-1)-.5)*.28,-.035+(y/max(1,f.h-1)-.5)*.15);z=0j;n=0
                while abs(z)<2 and n<32:z=complex(abs(z.real),abs(z.imag))**2+c;n+=1
                if n<32:f.put(x,y,'░▒▓█'[n%4],p[(n//3+int(t*.3))%5])

    def newton(self,f,t,p):
        roots=[complex(1,0),complex(-.5,.866),complex(-.5,-.866)]
        for y in range(f.h):
            for x in range(f.w):
                z=complex((x/max(1,f.w-1)-.5)*3,(y/max(1,f.h-1)-.5)*2.5)*complex(math.cos(t*.04),math.sin(t*.04))
                n=0
                for n in range(16):
                    if abs(z)<1e-6:break
                    nxt=z-(z*z*z-1)/(3*z*z)
                    if abs(nxt-z)<.001:z=nxt;break
                    z=nxt
                root=min(range(3),key=lambda i:abs(z-roots[i]));f.put(x,y,'░▒▓█'[min(3,n//4)],p[root])

    def apollonian(self,f,t,p):
        for y in range(f.h):
            for x in range(f.w):
                a=(x/f.w-.5)*3;b=(y/f.h-.5)*3;v=0
                for i in range(6):
                    a=abs(a)%2-1;b=abs(b)%2-1;r=max(.05,a*a+b*b);a=a/r+.12*math.sin(t*.1);b=b/r;v+=1/r
                if int(v*2)%4:f.put(x,y,'░▒▓'[int(v)%3],p[int(v)%5])

    def reaction(self,f,t,p):
        if 'reaction' not in self.state:
            w=min(90,max(4,f.w));h=min(45,max(4,f.h));rng=random.Random(17)
            self.state.update(reaction=[[rng.random()*.1+(1 if abs(x-w//2)<4 and abs(y-h//2)<4 else 0) for x in range(w)] for y in range(h)],rw=w,rh=h)
        grid=self.state['reaction'];w=self.state['rw'];h=self.state['rh']
        if int(t*12)!=self.last_step:
            for _ in range(3):
                grid=[[max(0,min(1,grid[y][x]+.18*(grid[y][(x-1)%w]+grid[y][(x+1)%w]+grid[(y-1)%h][x]+grid[(y+1)%h][x]-4*grid[y][x])+.08*grid[y][x]*(1-grid[y][x])*(grid[y][x]-.25))) for x in range(w)] for y in range(h)]
            self.state['reaction']=grid;self.last_step=int(t*12)
        for y in range(f.h):
            for x in range(f.w):
                v=grid[y*h//f.h][x*w//f.w]
                if v>.06:f.put(x,y,'░▒▓█'[min(3,int(v*4))],p[min(4,int(v*5))])

    def pacman(self,f,t,p):
        y=f.h//2;x=int(t*8)%(f.w+8)-4
        for px in range(0,f.w,4):f.put(px,y,'·',p[4])
        f.text(x,y,'ᗧ' if int(t*6)%2 else '●',p[4]);f.text(x-10,y,'╭╮',p[2]);f.text(x-10,y+1,'╰╯',p[2])

    def pong(self,f,t,p):
        x=(t*.13)%2;x=x if x<1 else 2-x;y=.5+.38*math.sin(t*1.9)
        for py in range(0,f.h,2):f.put(f.w//2,py,'┊',p[3])
        for side,phase in [(1,0),(f.w-2,.3)]:
            cy=int((.5+.35*math.sin(t*1.9+phase))*f.h)
            for d in range(-2,3):f.put(side,cy+d,'█',p[0])
        f.put(x*(f.w-5)+2,y*(f.h-2)+1,'●',p[4])

    def invaders(self,f,t,p):
        sprites=[' ▄█▄ ','▟███▙','▀ ▀ ▀'];shift=int(math.sin(t*.7)*f.w*.1)
        for row in range(3):
            for col in range(max(1,f.w//10)):
                for j,line in enumerate(sprites):f.text(col*10+shift+2,row*5+j+1,line,p[row])
        x=f.w//2+math.sin(t*.5)*f.w*.3;f.text(x,f.h-2,'╱█╲',p[4]);f.put(x+1,f.h-3-(t*10)%max(1,f.h-3),'│',p[0])

    def snake(self,f,t,p):
        step=int(t*10);length=max(8,min(40,f.w));width=max(1,f.w-2)
        for i in range(length):
            n=step-i;x=n%width+1;row=(n//width)%max(1,f.h-2)
            if row%2:x=width-x+1
            f.put(x,row+1,'●' if i==0 else '▪',p[0] if i<length//2 else p[1])
        f.put((step//30*17+7)%f.w,(step//30*7+3)%f.h,'◆',p[2])

    def sinescroller(self,f,t,p):
        text='  T T H I N G S   ·   S T A Y   C U R I O U S   ·   '
        for x in range(f.w):
            y=f.h/2+math.sin(x*.12-t*1.2)*f.h*.25
            f.put(x,y,text[(x+int(t*8))%len(text)],p[(x//8)%5])

    def maze3d(self,f,t,p):
        for depth in range(10):
            z=((depth+t*.7)%10)/10;s=(1-z)**2
            hw=f.w*.5*s;hh=f.h*.5*s;cx=f.w/2+math.sin(t*.2)*z*f.w*.1
            f.line(cx-hw,f.h/2-hh,cx+hw,f.h/2-hh,'─',p[depth%5]);f.line(cx-hw,f.h/2+hh,cx+hw,f.h/2+hh,'─',p[depth%5])
            f.line(cx-hw,f.h/2-hh,cx-hw,f.h/2+hh,'│',p[depth%5]);f.line(cx+hw,f.h/2-hh,cx+hw,f.h/2+hh,'│',p[depth%5])

    def toasters(self,f,t,p):
        for i in range(max(3,f.w*f.h//300)):
            x=(i*31-t*(3+i%3))%(f.w+14)-10;y=(i*11+t*.5)%max(1,f.h-3)
            f.text(x,y,' ╱╲  ╱╲ ' if int(t*3+i)%2 else ' ─┐  ┌─ ',p[3]);f.text(x,y+1,'╰[▤▤]╯',p[4]);f.text(x+2,y+2,'╰──╯',p[3])

    def tron(self,f,t,p):
        if 'trails' not in self.state:self.state['trails']=[]
        trails=self.state['trails']
        for i in range(4):
            phase=t*(.3+i*.05)+i*2;x=(.5+.4*math.sin(phase))*f.w;y=(.5+.4*math.sin(phase*.73+i))*f.h
            if int(t*15)!=self.last_step:trails.append((x,y,i))
        self.last_step=int(t*15);self.state['trails']=trails[-1500:]
        for x,y,i in self.state['trails']:f.put(x,y,'▪',p[i])

    def skyline(self,f,t,p):
        for i in range(max(5,f.w//5)):
            x=i*6;h=3+(i*17)%max(4,int(f.h*.7))
            for y in range(f.h-h,f.h):
                for dx in range(5):f.put(x+dx,y,'▪' if dx%2 and (y+i)%3==0 and math.sin(i*7+y+t*.05)>.1 else '▓',p[4] if dx%2 and (y+i)%3==0 else '#263c50')
        f.put(f.w*.8,f.h*.15,'☾',p[4])

    def doublependulum(self,f,t,p):
        pts=[]
        for i in range(850):
            u=t-i*.006;a=math.sin(u*.9)*2+math.sin(u*1.73);b=math.sin(u*1.43+.5)*2.5
            x=.45*math.sin(a)+.35*math.sin(b);y=.45*math.cos(a)+.35*math.cos(b)
            pts.append((f.w*(1+x),f.h*(1.4+y*2),p[i//170%5]))
        f.braille(pts)
        a=math.sin(t*.9)*2+math.sin(t*1.73);b=math.sin(t*1.43+.5)*2.5
        x1=f.w/2+math.sin(a)*f.w*.225;y1=f.h*.35+math.cos(a)*f.h*.225
        x2=x1+math.sin(b)*f.w*.175;y2=y1+math.cos(b)*f.h*.175
        f.line(f.w/2,f.h*.35,x1,y1,'·',p[0]);f.line(x1,y1,x2,y2,'·',p[2]);f.put(x2,y2,'●',p[4])

    def _chaotic(self,f,t,p,kind):
        cache='chaotic_'+kind
        if cache not in self.state:
            x,y,z=.1,.1,.1;points=[]
            for i in range(8000):
                if kind=='rossler':x,y,z=x+(-y-z)*.012,y+(x+.2*y)*.012,z+(.2+z*(x-5.7))*.012;px,py=x*.07,z*.08-.5
                elif kind=='clifford':x,y=math.sin(-1.4*y)+math.cos(-1.4*x),math.sin(1.6*x)+.7*math.cos(1.6*y);px,py=x*.45,y*.45
                elif kind=='dejong':x,y=math.sin(1.4*y)-math.cos(-2.3*x),math.sin(2.4*x)-math.cos(-2.1*y);px,py=x*.43,y*.43
                else:
                    a=.4-6/(1+x*x+y*y);x,y=1+.9*(x*math.cos(a)-y*math.sin(a)),.9*(x*math.sin(a)+y*math.cos(a));px,py=(x-.5)*.55,y*.55
                if i>300 and math.isfinite(px) and math.isfinite(py):points.append((px,py))
            self.state[cache]=points
        pts=[];a=math.sin(t*.1)*.15
        for i,(x,y) in enumerate(self.state[cache]):pts.append((f.w*(1+x*math.cos(a)-y*math.sin(a)),f.h*2*(1+x*math.sin(a)+y*math.cos(a)),p[i//1600%5]))
        f.braille(pts)

    def rossler(self,f,t,p):self._chaotic(f,t,p,'rossler')
    def clifford(self,f,t,p):self._chaotic(f,t,p,'clifford')
    def dejong(self,f,t,p):self._chaotic(f,t,p,'dejong')
    def ikeda(self,f,t,p):self._chaotic(f,t,p,'ikeda')
