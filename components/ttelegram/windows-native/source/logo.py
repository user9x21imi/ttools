"""Scalable terminal-native dotted Telegram mark, rendered as Braille cells."""
import shutil

PLANE = [(-.67,-.06),(.66,-.57),(.43,.64),(.06,.33),(-.13,.51),(-.12,.15)]
FOLD = [(-.12,.15),(.47,-.39),(.06,.33),(-.13,.51)]
CUT = [(-.12,.15),(.47,-.39),(-.01,.23)]

def inside(x,y,poly):
    result=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: result=not result
    return result

def render():
    size=shutil.get_terminal_size((100,36))
    h=max(5,min(26,size.lines-8,(size.columns-4)//2)); w=h*2
    indent=' '*max(0,(size.columns-w)//2)
    rows=[]
    dots=[(0,0,1),(0,1,2),(0,2,4),(1,0,8),(1,1,16),(1,2,32),(0,3,64),(1,3,128)]
    for row in range(h):
        cells=[]
        for col in range(w):
            mask=0; plane_count=0; fold_count=0
            for dx,dy,bit in dots:
                x=((col*2+dx+.5)/(w*2)*2-1)*1.04
                y=((row*4+dy+.5)/(h*4)*2-1)*1.04
                if x*x+y*y>1: continue
                mask|=bit
                if inside(x,y,PLANE):
                    plane_count+=1
                    if inside(x,y,FOLD): fold_count+=1
                    if inside(x,y,CUT): plane_count-=1
            if not mask: cells.append(' '); continue
            if plane_count>=4: color=(211,235,249) if fold_count>=3 else (250,253,255)
            else:
                t=row/max(1,h-1); color=(int(55-28*t),int(187-53*t),int(245-25*t))
            cells.append('\033[38;2;%d;%d;%dm'%color+chr(0x2800+mask))
        rows.append(indent+''.join(cells)+'\033[0m')
    return '\n'.join(rows)
