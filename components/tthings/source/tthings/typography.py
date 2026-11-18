"""Code-native pixel typography for terminal dashboards."""
from .effects import Frame,DIGITS

# Compact five-row signage, with proportional punctuation.
GLYPHS={**DIGITS,
'%':['101','001','010','100','101'],'.':['0','0','0','0','1'],
'-':['000','000','111','000','000'],'/':['001','001','010','100','100'],
' ':['0']*5,'?':['111','001','011','000','010'],
'A':['010','101','111','101','101'],'B':['110','101','110','101','110'],
'C':['111','100','100','100','111'],'D':['110','101','101','101','110'],
'E':['111','100','110','100','111'],'F':['111','100','110','100','100'],
'G':['111','100','101','101','111'],'H':['101','101','111','101','101'],
'I':['111','010','010','010','111'],'J':['001','001','001','101','111'],
'K':['101','101','110','101','101'],'L':['100','100','100','100','111'],
'M':['101','111','111','101','101'],'N':['101','111','111','111','101'],
'O':['111','101','101','101','111'],'P':['111','101','111','100','100'],
'Q':['111','101','101','111','001'],'R':['110','101','110','101','101'],
'S':['111','100','111','001','111'],'T':['111','010','010','010','010'],
'U':['101','101','101','101','111'],'V':['101','101','101','101','010'],
'W':['101','101','111','111','101'],'X':['101','101','010','101','101'],
'Y':['101','101','010','010','010'],'Z':['111','001','010','100','111']}
STYLES=('blocks','dots','wire','braille')
STYLE_LABELS=('Блоки','Точки','Контур','Брайль')


def text_units(text):return sum(len(GLYPHS.get(c.upper(),GLYPHS['?'])[0])+1 for c in text)-1 if text else 0


def number_art(text,width,height=5,style='blocks',size=0):
    """Return a transparent glyph layer. Never crop away meaningful digits."""
    width=max(1,width);height=max(1,height);style=style if style in STYLES else 'blocks'
    units=max(1,text_units(text))
    if style=='braille':
        sx=max(1,min(4+size,(width*2)//units));sy=max(1,min(2+size,(height*4)//5))
        sx=max(1,sx);sy=max(1,sy)
        if units>width*2 or height<2:
            result=Frame(min(width,len(text)),1);result.text(0,0,text);return result
        result=Frame(min(width,(units*sx+1)//2),min(height,(5*sy+3)//4));points=[];x=0
        for char in text.upper():
            glyph=GLYPHS.get(char,GLYPHS['?'])
            for gy,row in enumerate(glyph):
                for gx,pixel in enumerate(row):
                    if pixel=='1':
                        for dy in range(sy):
                            for dx in range(sx):points.append((x+gx*sx+dx,gy*sy+dy,'#ffffff'))
            x+=(len(glyph[0])+1)*sx
        result.braille(points);return result
    if units>width or height<5:
        result=Frame(min(width,len(text)),1);result.text(0,0,text);return result
    sx=max(1,min(2+size,width//units));sy=max(1,min(1+max(0,size-1),height//5))
    result=Frame(units*sx,5*sy);x=0
    for char in text.upper():
        glyph=GLYPHS.get(char,GLYPHS['?'])
        for gy,row in enumerate(glyph):
            for gx,pixel in enumerate(row):
                if pixel!='1':continue
                for dy in range(sy):
                    for dx in range(sx):
                        if style=='dots':ink='●' if dx==0 and dy==0 else ' '
                        elif style=='wire':
                            neighbors=(gx>0 and row[gx-1]=='1',gx+1<len(row) and row[gx+1]=='1',gy>0 and glyph[gy-1][gx]=='1',gy+1<len(glyph) and glyph[gy+1][gx]=='1')
                            left,right,up,down=neighbors
                            ink={ (False,True,False,True):'┌',(True,False,False,True):'┐',(False,True,True,False):'└',(True,False,True,False):'┘',
                                  (True,True,False,False):'─',(False,False,True,True):'│',
                                  (False,True,False,False):'╶',(True,False,False,False):'╴',(False,False,True,False):'╵',(False,False,False,True):'╷' }.get(neighbors,'┼' if sum(neighbors)>2 else '▪')
                            if dx:ink='─' if right and not dy else ' '
                            if dy:ink='│' if down and not dx else ' '
                        else:ink='█'
                        result.put(x+gx*sx+dx,gy*sy+dy,ink)
        x+=(len(glyph[0])+1)*sx
    return result


def big_text(frame,x,y,text,color,width=None,height=5,style='blocks',size=0):
    art=number_art(text,width if width is not None else max(1,frame.w-x),height,style,size)
    for py,row in enumerate(art.cells):
        for px,(char,_) in enumerate(row):
            if char!=' ':frame.put(x+px,y+py,char,color)
    return art.w,art.h


def metric_hero(frame,label,value,unit,color,x=2,y=4,width=None,style='blocks',size=0):
    width=max(1,width if width is not None else frame.w-x-2)
    frame.text(x,y,label,color)
    _,height=big_text(frame,x,y+2,value,color,width=width,height=5+max(0,size-1)*5,style=style,size=size)
    frame.text(x,y+3+height,unit,'#75899d')
    return y+4+height
