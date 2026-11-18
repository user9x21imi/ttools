"""Seventy original terminal interpretations of mathematical and demoscene motifs.

Shared sampling/projection is reused; each entry has its own construction.
No third-party code, textures, binaries or network requests at runtime.
"""
import math
import random

TAU=math.tau
REGISTRY=[]
def group(family,category,items):
    for key,title,description in items:REGISTRY.append((key,title,category,description,family))

group('surface','Математические поверхности',[
('dini_surface','Поверхность Дини','Закрученная псевдосфера с логарифмическим профилем'),
('enneper_surface','Поверхность Эннепера','Самопересекающаяся минимальная поверхность'),
('helicoid_surface','Геликоид','Винтовая поверхность вокруг вертикальной оси'),
('catenoid_surface','Катеноид','Талия поверхности из цепных линий'),
('astroid_surface','Астроидальная сфера','Грани из кубов синусов и косинусов'),
('roman_surface','Римская поверхность','Три симметричных самопересечения'),
('crosscap_surface','Кросс-кап','Перекрученный диск с самопересечением'),
('superellipsoid','Суперэллипсоид','Плавное превращение округлого куба в звезду'),
('cyclide_surface','Циклида','Смещённые кольцевые сечения'),
('saddle_surface','Седло','Гиперболический параболоид с движущимися сечениями'),
('conoid_surface','Коноид','Линейчатая поверхность с синусной осью'),
('seashell_fan','Веер раковины','Радиальные рёбра раскрытой раковины'),
])
group('curve','Световые кривые',[
('viviani_curve','Кривая Вивиани','Пересечение сферы и цилиндра'),
('clelia_curve','Кривая Клелии','Замкнутая орбита на сфере'),
('spherical_spiral','Сферическая спираль','Световая нить от полюса к полюсу'),
('butterfly_curve','Кривая-бабочка','Трансцендентный четырёхкрылый контур'),
('epicycloid_curve','Эпициклоида','Круг обкатывает другой круг снаружи'),
('hypocycloid_curve','Гипоциклоида','Круг обкатывает другой круг изнутри'),
('cochleoid_curve','Кохлеоида','Система вложенных лепестков sinc'),
('tractrix_curve','Трактриса','Зеркальные ветви с асимптотой'),
('involute_curve','Эвольвента','Разматывающаяся нить окружности'),
('cardioid_braid','Кардиоидная коса','Переплетение нескольких сердцевидных контуров'),
('folium_curve','Лист Декарта','Замкнутая петля кубической кривой'),
('fermat_spiral','Спираль Ферма','Две противоположные ветви квадратного корня'),
])
group('map','Хаотические карты',[
('hopalong_map','Hopalong','Корневое отображение с угловатыми орбитами'),
('bedhead_map','Bedhead','Синусоидальное отображение с разветвлёнными крыльями'),
('gumowski_map','Гумовский—Мира','Рациональное отображение с зеркальными лепестками'),
('gingerbread_map','Пряничное отображение','Орбиты кусочно-линейного отображения'),
('henon_map','Отображение Эно','Складки квадратичного дискретного отображения'),
('tinkerbell_map','Тинкербелл','Серп из квадратичных комплексных итераций'),
('standard_map','Стандартное отображение','Островки фазового пространства на торе'),
('popcorn_map','Popcorn','Нелинейное поле синусов и тангенсов'),
('sine_lattice','Синусная решётка','Связанные колебания двух координат'),
('swirl_ifs','Спиральный IFS','Нелинейные свёртки системы сжатий'),
])
group('field','Оптические поля',[
('domain_warp','Искажение пространства','Двойное искривление координат синусным полем'),
('ridged_field','Горные гребни','Многомасштабные острые световые хребты'),
('fbm_clouds','Облачный атлас','Пять масштабов плавно меняющегося шума'),
('voronoi_edges','Границы Вороного','Светящиеся границы движущихся ячеек'),
('voronoi_glass','Цветное стекло','Мозаика из движущихся центров Вороного'),
('electric_filaments','Электрические нити','Ветвящиеся горизонтальные разряды'),
('lens_array','Массив линз','Периодические линзы искривляют полосы'),
('hex_pulse','Пульсирующие соты','Волны проходят по шестиугольным контурам'),
('prism_fan','Призматический веер','Вращающиеся цветовые клинья'),
('moire_spokes','Радиальный муар','Интерференция повёрнутых лучевых решёток'),
('chromatic_waves','Хроматические волны','Разделение каналов трёх волн'),
('marble_veins','Мраморные жилы','Тонкие жилы в турбулентном координатном поле'),
])
group('particles','Потоки и орбиты',[
('flurry_streams','Flurry · потоки','Несколько текучих шлейфов частиц'),
('galaxy_collision','Столкновение галактик','Два вращающихся звёздных диска с приливными хвостами'),
('solar_wind','Солнечный ветер','Лучи частиц огибают магнитную оболочку'),
('rain_curtain','Дождевая завеса','Наклонённые тонкие струны с порывами ветра'),
('bokeh_drift','Дрейф боке','Размытые кольцевые огни на разных глубинах'),
('magnetic_bottle','Магнитная ловушка','Спирали сужаются к двум полюсам'),
('beam_splitter','Расщепление луча','Пучок разделяется на спектральные траектории'),
('cloud_chamber','Камера частиц','Тонкие дуговые треки с затухающими хвостами'),
('granular_rings','Пылевые кольца','Вложенные диски с плотностными волнами'),
('levitating_dust','Левитирующая пыль','Подсвеченная пыль в стоячей волне'),
])
group('demo','Демосцена',[
('rotozoom','Ротозум','Вращение и масштабирование процедурной текстуры'),
('twister','Твистер','Винтовая колонна с затенёнными гранями'),
('shadebobs','Shadebobs','Мягкие световые пятна с длинным следом'),
('vectorballs','Векторные шары','Сфера из освещённых объёмных бусин'),
('rasterbars','Растровые полосы','Перекрывающиеся световые полосы по синусным траекториям'),
('copperwaves','Медные волны','Рябь цветовых полос со смещением по строкам'),
('dot_tunnel','Точечный тоннель','Перспективные кольца из бегущих точек'),
('wire_city','Каркасный мегаполис','Полёт вдоль прозрачных объёмных кварталов'),
])
group('pattern','Орнаменты',[
('truchet_tiles','Плитки Трюше','Связанные четверти окружностей на сетке'),
('star_tessellation','Звёздная мозаика','Сцепленные восьмиконечные контуры'),
('guilloche','Гильоше','Многослойные тонкие защитные розетки'),
('braided_grid','Плетёная сетка','Горизонтальные и вертикальные волнистые нити'),
('hex_lattice','Шестигранная решётка','Дыхание ячеек в объёмной перспективе'),
('circle_packing','Круговая упаковка','Каскады окружностей в шестиугольной упаковке'),
])
assert len(REGISTRY)==70

def shade(p,position,light=1):
    position=max(0,min(.999,position))*4;a=int(position);b=min(4,a+1);q=position-a
    rgb=[int((int(p[a][i:i+2],16)*(1-q)+int(p[b][i:i+2],16)*q)*max(0,min(1,light))) for i in (1,3,5)]
    return '#%02x%02x%02x'%tuple(rgb)

class GalleryEffects:
    def _gallery_project(self,f,points,t,p,scale=.8,rotate=True):
        ca,sa=math.cos(t*.17),math.sin(t*.17);result=[]
        for point in points:
            x,y,z,c=point
            if not all(math.isfinite(v) for v in (x,y,z)):continue
            if rotate:x,z=x*ca+z*sa,z*ca-x*sa
            y,z=y*.94-z*.34,y*.34+z*.94;depth=3/max(.8,3-z)
            result.append((f.w+x*f.w*scale*depth,f.h*2+y*f.h*scale*2*depth,p[int(c)%5]))
        f.braille(result)

    def _gallery_surface(self,f,t,p,key):
        pts=[];rows=20;cols=min(190,max(80,f.w*2))
        power=.55+.35*math.sin(t*.17)
        for j in range(rows):
            v=j/(rows-1)
            for i in range(cols):
                u=i/(cols-1);a=u*TAU;b=v*TAU
                if key=='dini_surface':
                    b=.16+v*2.65;a=u*TAU*1.4
                    x=.55*math.cos(a)*math.sin(b);z=.55*math.sin(a)*math.sin(b);y=.55*(math.cos(b)+math.log(math.tan(b/2)))+.12*a-.4
                elif key=='enneper_surface':
                    a=(u-.5)*2.1;b=(v-.5)*2.1;x=(a-a**3/3+a*b*b)*.45;y=(b-b**3/3+b*a*a)*.45;z=(a*a-b*b)*.38
                elif key=='helicoid_surface':
                    r=(v-.5)*1.5;a=u*TAU*2;x=r*math.cos(a);z=r*math.sin(a);y=(u-.5)*1.6
                elif key=='catenoid_surface':
                    y=(v-.5)*1.5;r=.32*math.cosh(y*1.7);x=r*math.cos(a);z=r*math.sin(a)
                elif key=='astroid_surface':
                    b=(v-.5)*math.pi;x=math.cos(b)**3*math.cos(a)**3;y=math.sin(b)**3;z=math.cos(b)**3*math.sin(a)**3
                elif key=='roman_surface':
                    b=v*math.pi;x=math.sin(2*a)*math.sin(b)**2;y=math.sin(a)*math.sin(2*b);z=math.cos(a)*math.sin(2*b)
                    x*=.7;y*=.7;z*=.7
                elif key=='crosscap_surface':
                    b=v*math.pi;x=.8*math.sin(a)*math.sin(2*b);y=.8*math.sin(2*a)*math.sin(b)**2;z=.8*(math.cos(2*a)*math.sin(b)**2-.5)
                elif key=='superellipsoid':
                    b=(v-.5)*math.pi
                    sp=lambda q:math.copysign(abs(q)**power,q)
                    x=sp(math.cos(b))*sp(math.cos(a))*.7;y=sp(math.sin(b))*.7;z=sp(math.cos(b))*sp(math.sin(a))*.7
                elif key=='cyclide_surface':
                    r=.55+.2*math.cos(b);x=r*math.cos(a)+.2*math.cos(b);z=r*math.sin(a);y=.3*math.sin(b)*(1+.4*math.cos(a))
                elif key=='saddle_surface':
                    x=(u-.5)*1.7;z=(v-.5)*1.7;y=(x*x-z*z)*.6
                elif key=='conoid_surface':
                    x=(v-.5)*1.6*math.cos(a);z=(v-.5)*1.6*math.sin(a);y=.55*math.sin(a*2)
                else:
                    a=(u-.5)*math.pi*1.35;r=.15+v*.85;x=r*math.sin(a);y=r*math.cos(a)-.4;z=.2*math.sin(a*17)*(v**.6)
                pts.append((x,y,z,j//4))
        self._gallery_project(f,pts,t,p,.7)

    def _gallery_curve(self,f,t,p,key):
        pts=[];n=min(4000,max(1000,f.w*f.h*2))
        for i in range(n):
            u=i/(n-1);a=u*TAU;layer=i%5;z=.08*math.sin(a*3+t*.25)
            if key=='viviani_curve':x=.55*(1+math.cos(a))-.55;y=.55*math.sin(a);z=.9*math.sin(a/2)
            elif key=='clelia_curve':x=math.cos(a)*math.sin(5*a);y=math.sin(a)*math.sin(5*a);z=math.cos(5*a)
            elif key=='spherical_spiral':b=(u-.5)*math.pi;a*=9;x=math.cos(b)*math.cos(a);y=math.sin(b);z=math.cos(b)*math.sin(a)
            elif key=='butterfly_curve':
                r=math.exp(math.cos(a))-2*math.cos(4*a)-math.sin(a/12)**5;x=math.sin(a)*r*.28;y=-math.cos(a)*r*.28
            elif key=='epicycloid_curve':x=(4*math.cos(a)-math.cos(4*a))*.18;y=(4*math.sin(a)-math.sin(4*a))*.18
            elif key=='hypocycloid_curve':x=(3*math.cos(a)+math.cos(3*a))*.22;y=(3*math.sin(a)-math.sin(3*a))*.22
            elif key=='cochleoid_curve':
                a=(u-.5)*28;r=math.sin(a)/a if abs(a)>.001 else 1;x=r*math.cos(a);y=r*math.sin(a)
            elif key=='tractrix_curve':
                a=.04+u*3.2;x=(a-math.tanh(a))*.45-.7;y=1/math.cosh(a)*1.5-.7
                if i%2:x=-x
            elif key=='involute_curve':
                a=u*TAU*2;x=(math.cos(a)+a*math.sin(a))*.075;y=(math.sin(a)-a*math.cos(a))*.075
            elif key=='cardioid_braid':
                a+=t*.12;r=.45*(1-math.cos(a*3));x=r*math.cos(a);y=r*math.sin(a);z=.16*math.sin(a*9)
            elif key=='folium_curve':
                a=u*10;den=1+a**3;x=3*a/den-.65;y=3*a*a/den-.65
            else:
                a=u*TAU*6+t*.12;r=math.sqrt(u)*.9;x=r*math.cos(a);y=r*math.sin(a)
                if i%2:x=-x;y=-y
            # Adjacent subpixel tracks soften thin curves without changing their shape.
            pts.append((x+.007*math.sin(t+a),y,z,layer))
        self._gallery_project(f,pts,t,p,.7)

    def _gallery_map(self,f,t,p,key):
        cache=self.state.get('gallery_map')
        if cache is None:
            rng=random.Random(127);x,y=.1,.2;raw=[];n=6500
            def mira(q):return .008*q+2*(1-.008)*q*q/(1+q*q)
            for i in range(n+100):
                if key=='hopalong_map':x,y=y-math.copysign(math.sqrt(abs(1.1*x-.3)),x),.7-x
                elif key=='bedhead_map':x,y=math.sin(x*y/1.3)*y+math.cos(.7*x-y),x+math.sin(y)*.7
                elif key=='gumowski_map':xx=y+mira(x);x,y=xx,-x+mira(xx)
                elif key=='gingerbread_map':x,y=1-y+abs(x),x
                elif key=='henon_map':x,y=1-1.4*x*x+y,.3*x
                elif key=='tinkerbell_map':x,y=x*x-y*y+.9*x-.6013*y,2*x*y+2*x+.5*y
                elif key=='standard_map':y=(y+.95*math.sin(x))%TAU;x=(x+y)%TAU
                elif key=='popcorn_map':
                    if i%80==0:x,y=rng.uniform(-3,3),rng.uniform(-3,3)
                    x,y=x-.05*math.sin(y+math.tan(3*y)),y-.05*math.sin(x+math.tan(3*x))
                elif key=='sine_lattice':x,y=math.sin(1.7*y)+.7*math.cos(1.3*x),math.sin(1.4*x)-.6*math.cos(1.9*y)
                else:
                    branch=rng.randrange(3);xx=.65*x+.25*y+(branch-1)*.55;yy=-.25*x+.65*y+.3*math.sin(branch*2)
                    r=xx*xx+yy*yy;x,y=xx*math.sin(r)-yy*math.cos(r),xx*math.cos(r)+yy*math.sin(r)
                if not math.isfinite(x+y) or abs(x)+abs(y)>80:x,y=rng.random()*.2,rng.random()*.2
                if key=='gingerbread_map' and i%97==0:x,y=rng.uniform(-2,2),rng.uniform(-2,2)
                if i>100:raw.append((x,y))
            xs=sorted(x for x,y in raw);ys=sorted(y for x,y in raw);lo,hi=xs[len(xs)//100],xs[-len(xs)//100];bottom,top=ys[len(ys)//100],ys[-len(ys)//100]
            sx=max(.01,hi-lo);sy=max(.01,top-bottom)
            cache=[((x-(lo+hi)/2)/sx*1.65,(y-(bottom+top)/2)/sy*1.45) for x,y in raw];self.state['gallery_map']=cache
        pts=[(x,y,.09*math.sin(i*.03+t*.25),(i//400)%5) for i,(x,y) in enumerate(cache)]
        self._gallery_project(f,pts,t,p,.8)

    def _gallery_raster_limit(self,f,t,p,key,family):
        # Expensive scalar fields keep a bounded sample count on very large terminals.
        factor=max(f.w/160,f.h/64)
        if factor<=1:return False
        from .effects import Frame
        small=Frame(max(1,int(f.w/factor)),max(1,int(f.h/factor)))
        getattr(self,'_gallery_'+family)(small,t,p,key)
        indices=[min(small.w-1,x*small.w//f.w) for x in range(f.w)]
        for y in range(f.h):
            source=small.cells[min(small.h-1,y*small.h//f.h)]
            f.cells[y]=[source[x] for x in indices]
        return True

    def _gallery_field(self,f,t,p,key):
        if self._gallery_raster_limit(f,t,p,key,'field'):return
        def wave(x,y):return math.sin(x*1.7+math.sin(y*1.3))+math.cos(y*2.1+math.sin(x*.9))
        centers=[(math.sin(i*2.3+t*.11)*1.4,math.cos(i*1.7+t*.13)) for i in range(9)]
        chars=' .·:░▒▓█';colors=[shade(p,i/63,.3+.7*i/63) for i in range(64)]
        for y in range(f.h):
            v=(y/max(1,f.h)-.5)*2
            for x in range(f.w):
                u=(x/max(1,f.w)-.5)*2*f.w/max(1,f.h)*.5;r=math.hypot(u,v);a=math.atan2(v,u)
                if key=='domain_warp':q=wave(u*2+math.sin(v*3+t*.23),v*2+math.cos(u*3-t*.2));value=(math.sin(q*3+t*.2)+1)/2
                elif key=='ridged_field':value=sum((1-abs(math.sin(u*(2**k)+math.cos(v*(2**k)+t*.12))))/(2**k) for k in range(1,5))
                elif key=='fbm_clouds':value=.5+sum(wave(u*(2**k)+t*.07,v*(2**k)-t*.04)/(2**(k+3)) for k in range(5))
                elif key in ('voronoi_edges','voronoi_glass'):
                    d=sorted((math.hypot(u-cx,v-cy),i) for i,(cx,cy) in enumerate(centers))
                    value=max(0,1-(d[1][0]-d[0][0])*12) if key=='voronoi_edges' else (.25+d[0][1]/12)*(1-min(.6,d[0][0]*.6))
                elif key=='electric_filaments':value=max(math.exp(-abs(v-math.sin(u*5+t*.7+i)*.4-math.sin(u*17-t*.8)*.06-i*.4+.6)*70) for i in range(4))
                elif key=='lens_array':
                    xx=(u*3+.5)%1-.5;yy=(v*3+.5)%1-.5;value=(math.sin(u*17+t*.4+math.exp(-(xx*xx+yy*yy)*14)*4)+1)/2
                elif key=='hex_pulse':
                    xx=u*5;yy=v*5;xx-=round(yy)*.5;xx-=round(xx);yy-=round(yy);edge=max(abs(xx)*.866+abs(yy)*.5,abs(yy));value=math.exp(-abs(edge-.42)*35)*(.55+.45*math.sin(r*8-t))
                elif key=='prism_fan':value=(math.sin(a*13+t*.35+r*3)+1)/2
                elif key=='moire_spokes':value=(math.cos(a*25)+math.cos(math.atan2(v+.15*math.sin(t*.2),u+.2)*25+t*.15)+2)/4
                elif key=='chromatic_waves':value=(math.sin(u*9+t*.4)+math.sin(v*11-t*.35)+math.sin((u+v)*7+t*.2)+3)/6
                else:value=math.exp(-abs(math.sin(u*7+wave(u*3+t*.1,v*3)*2))*9)
                value=max(0,min(.999,value));f.put(x,y,chars[int(value*len(chars))],colors[int(value*63)])

    def _gallery_particles(self,f,t,p,key):
        pts=[];n=min(3800,max(700,f.w*f.h*2))
        for i in range(n):
            u=i/n;a=i*2.399963;phase=(t*.08+u)%1
            if key=='flurry_streams':
                k=i%4;age=(u*5+t*.16)%1;x=math.sin(age*5+k*1.7+t*.15)*(.1+age*.8);y=(age-.5)*1.7;z=math.cos(age*6+k)*age*.5
            elif key=='galaxy_collision':
                k=i%2;r=math.sqrt(u)*.58;angle=a+t*(.14 if k else -.14)+r*5
                x=r*math.cos(angle)+(k-.5)*(.8+.2*math.sin(t*.1));z=r*math.sin(angle);y=math.sin(a)*.06+(k-.5)*.15
            elif key=='solar_wind':
                x=(phase-.5)*2;y=math.sin(a)*(.2+.65*math.exp(-x*x*4));z=math.cos(a)*(.2+.65*math.exp(-x*x*4))
            elif key=='rain_curtain':x=math.sin(i*73.7)*.95+.12*math.sin(t*.7+phase*3);y=(phase-.5)*2;z=math.sin(i*13.1)*.6
            elif key=='bokeh_drift':
                k=i%19;r=.035+(k%5)*.012;x=math.sin(k*13.3+t*.06)+math.cos(a)*r;y=math.cos(k*7.7+t*.09)*.8+math.sin(a)*r;z=math.sin(k)*.4
            elif key=='magnetic_bottle':
                y=(u-.5)*1.8;r=.12+.45*math.sin(u*math.pi)**2;x=r*math.cos(a+t*.5);z=r*math.sin(a+t*.5)
            elif key=='beam_splitter':
                x=(phase-.5)*2;k=i%5;y=max(0,x)*(.3*(k-2))*(1+.12*math.sin(t*.4))+math.sin(a)*.012;z=math.cos(a)*.04
            elif key=='cloud_chamber':
                k=i%17;age=(u*4+t*.05)%1;angle=age*3+k*2
                x=math.sin(k*3.1)*.5+math.sin(angle)*age*.5;y=math.cos(k*2.7)*.5+math.cos(angle)*age*.5;z=.1*math.sin(k)
            elif key=='granular_rings':
                r=.22+(i%7)*.1;angle=a+t*.2/r;x=r*math.cos(angle);z=r*math.sin(angle);y=.03*math.sin(angle*5+t*.5+r*9)
            else:x=math.sin(a)*.9;y=math.sin(i*7.1)*.75+.1*math.sin(t*.5+i);z=.2*math.sin(a*3+t*.25)
            pts.append((x,y,z,i%5))
        self._gallery_project(f,pts,t,p,.8,rotate=key not in ('rain_curtain','beam_splitter'))

    def _gallery_demo(self,f,t,p,key):
        if key=='dot_tunnel':
            pts=[]
            for j in range(30):
                depth=(j/30+t*.06)%1;r=.04+depth*1.5
                for i in range(70):
                    a=i/70*TAU+t*.13;pts.append((f.w+math.cos(a)*f.w*r,f.h*2+math.sin(a)*f.h*2*r,p[j%5]))
            f.braille(pts);return
        if key=='wire_city':
            pts=[]
            for j in range(10):
                depth=(j/10+t*.08)%1;z=.95-depth*1.8
                for side in (-1,1):
                    bx=side*.53;height=.18+(j*7%5)*.075;bw=side*.28
                    vertices=[(bx+dx*bw,-.42+dy*height,z+dz*.14) for dx in (0,1) for dy in (0,1) for dz in (0,1)]
                    for index,start in enumerate(vertices):
                        for bit in (1,2,4):
                            end_index=index^bit
                            if end_index<index:continue
                            end=vertices[end_index]
                            for k in range(16):
                                q=k/15;pts.append(tuple(start[a]*(1-q)+end[a]*q for a in range(3))+(j%5,))
            self._gallery_project(f,pts,0,p,.65,False);return
        if key=='vectorballs':
            pts=[]
            for i in range(95):
                y=1-2*i/94;r=math.sqrt(max(0,1-y*y));a=i*2.39996
                cx=r*math.cos(a)*.65;cy=y*.65;cz=r*math.sin(a)*.65
                for k in range(30):
                    q=k/30*TAU;pts.append((cx+.045*math.cos(q),cy+.045*math.sin(q),cz,i%5))
            self._gallery_project(f,pts,t,p,.8);return
        if self._gallery_raster_limit(f,t,p,key,'demo'):return
        colors=[shade(p,i/63) for i in range(64)]
        for y in range(f.h):
            v=y/max(1,f.h)*2-1
            for x in range(f.w):
                u=(x/max(1,f.w)*2-1)*f.w/max(1,f.h)*.5
                if key=='rotozoom':
                    scale=4+2*math.sin(t*.2);a=t*.12;xx=(u*math.cos(a)-v*math.sin(a))*scale;yy=(u*math.sin(a)+v*math.cos(a))*scale
                    value=(math.sin(xx*3)*math.sin(yy*3)+1)/2
                elif key=='twister':
                    center=math.sin(v*2+t*.35)*.25;angle=v*2.5+t*.45;bound=.25+.12*math.sin(angle)
                    if abs(u-center)>bound:continue
                    value=(math.cos((u-center)/bound*math.pi+angle)+1)/2
                elif key=='shadebobs':
                    value=min(1,sum(math.exp(-((u-math.sin(t*.3+i*.22)*.7)**2+(v-math.cos(t*.25+i*.24)*.6)**2)*70)*(1-i/28) for i in range(24)))
                elif key=='rasterbars':value=min(1,sum(math.exp(-abs(v-math.sin(t*.35+i*.9)*.7)*25) for i in range(6)))
                else:value=(math.sin(v*20+math.sin(u*4+t*.3)*3+t*.4)+1)/2
                value=max(0,min(.999,value));f.put(x,y,' ░▒▓█'[int(value*5)],colors[int(value*63)])

    def _gallery_pattern(self,f,t,p,key):
        pts=[]
        if key=='guilloche':
            for j in range(8):
                for i in range(900):
                    a=i/899*TAU;r=.55+.2*math.cos(a*13+j*.12+t*.18)
                    pts.append((r*math.cos(a),r*math.sin(a),.03*j,j%5))
        else:
            rows=6;cols=9
            for j in range(rows):
                for i in range(cols):
                    cx=(i-(cols-1)/2)*.25;cy=(j-(rows-1)/2)*.27
                    if key in ('hex_lattice','circle_packing'):cx+=(j%2)*.125
                    for k in range(70):
                        a=k/69*TAU;z=.07*math.sin(cx*3+cy*3+t*.3)
                        if key=='truchet_tiles':
                            quadrant=(i*7+j*13)%4;a=k/69*math.pi/2+quadrant*math.pi/2;r=.23;x=cx+r*math.cos(a);y=cy+r*math.sin(a)
                        elif key=='star_tessellation':
                            r=.1+.045*math.cos(a*8+t*.15);x=cx+r*math.cos(a);y=cy+r*math.sin(a)
                        elif key=='braided_grid':
                            q=k/69;x=cx+(q-.5)*.27;y=cy+.035*math.sin(q*TAU+t*.35+i)
                            pts.append((cx+.035*math.sin(q*TAU-t*.35+j),cy+(q-.5)*.27,z,i%5))
                        elif key=='hex_lattice':
                            edge=int(a/(TAU/6));q=(a%(TAU/6))/(TAU/6);aa=edge*TAU/6;bb=aa+TAU/6;r=.125
                            x=cx+r*(math.cos(aa)*(1-q)+math.cos(bb)*q);y=cy+r*(math.sin(aa)*(1-q)+math.sin(bb)*q)
                        else:r=.11*(.75+.2*math.sin(t*.3+i+j));x=cx+r*math.cos(a);y=cy+r*math.sin(a)
                        pts.append((x,y,z,(i+j)%5))
        self._gallery_project(f,pts,t*.2,p,.75)

def _renderer(key,family):
    def render(self,frame,elapsed,palette):getattr(self,'_gallery_'+family)(frame,elapsed,palette,key)
    render.__name__=key
    return render
for _key,_title,_category,_description,_family in REGISTRY:
    setattr(GalleryEffects,_key,_renderer(_key,_family))
