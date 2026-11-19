"""Quiet, bounded backgrounds built from the bundled tthings renderer API."""
import importlib.util
from functools import lru_cache
from pathlib import Path
import random
import sys
import time
from .visuals.effects import Frame,Scene as FallbackScene

PREFERRED=('light_bloom','rose','light_ribbons','phyllotaxis','porcelain','light_silk','dune_contours','guilloche')
FALLBACK=('particles','stars','sakura')

@lru_cache(maxsize=1)
def renderer_api():
    root=Path(__file__).resolve().parents[1]/'components/tthings/source/tthings'
    if not (root/'renderer.py').is_file():return None
    name='_ttools_bundled_things'
    spec=importlib.util.spec_from_file_location(name,root/'__init__.py',submodule_search_locations=[str(root)])
    package=importlib.util.module_from_spec(spec);sys.modules[name]=package;spec.loader.exec_module(package)
    return __import__(name+'.renderer',fromlist=['create_renderer'])

class Scene:
    """Keep the old render(width,height,time) call while using the stable SDK."""
    def __init__(self,name,seed=None):
        api=renderer_api();self.name=name;self.size=None
        if api is None:
            self.renderer=None;self.fallback=FallbackScene(name if hasattr(FallbackScene,name) else 'particles',seed)
        else:self.renderer=api.create_renderer(name,1,1,seed=seed,brightness=1.,max_fps=10)
    def render(self,width,height,elapsed):
        if self.renderer is None:return self.fallback.render(width,height,elapsed)
        if self.size!=(width,height):self.renderer.resize(width,height);self.size=(width,height)
        return self.renderer.render(elapsed)

class Background:
    MAX_WIDTH=180
    MAX_HEIGHT=72
    FRAME_INTERVAL=.1
    TRANSITION=1.2
    def __init__(self,*,seed=None,effect=None,now=None,motion=True,low_power=False):
        if low_power:self.MAX_WIDTH=96;self.MAX_HEIGHT=32;self.FRAME_INTERVAL=.25
        self.random=random.Random(seed)
        api=renderer_api()
        available={entry['id'] for entry in api.available_effects()} if api else set(FALLBACK)
        self.pool=tuple(name for name in PREFERRED if name in available) or FALLBACK
        if effect is not None and effect not in available:raise ValueError('Unknown effect: '+effect)
        self.effect=effect or ('phyllotaxis' if 'phyllotaxis' in available else self.pool[0])
        self.scene=Scene(self.effect,seed=self.random.randrange(2**31))
        self.secondary=('rose' if effect is None and 'rose' in available else self.random.choice([name for name in self.pool if name!=self.effect] or self.pool))
        self.overlay=Scene(self.secondary,seed=self.random.randrange(2**31))
        self.wall=time.monotonic() if now is None else now
        self.logical=0.;self.started=0.;self.paused=not motion
        self.next_switch=self.random.uniform(30,120)
        self.cached=None;self.previous=None;self.last_render=-1.;self.size=None
    def advance(self,now):
        if not self.paused:self.logical+=max(0.,now-self.wall)
        self.wall=now
    def change(self,now=None):
        self.advance(time.monotonic() if now is None else now)
        self.previous=None if self.paused else self.cached
        choices=[name for name in self.pool if name!=self.effect]
        self.effect=self.random.choice(choices or self.pool)
        self.scene=Scene(self.effect,seed=self.random.randrange(2**31))
        self.secondary=self.random.choice([name for name in self.pool if name!=self.effect] or self.pool)
        self.overlay=Scene(self.secondary,seed=self.random.randrange(2**31))
        self.started=self.logical;self.next_switch=self.logical+self.random.uniform(30,120)
        self.cached=None;self.last_render=-1.
    def toggle(self,now=None):
        self.advance(time.monotonic() if now is None else now)
        self.paused=not self.paused
    def render(self,width,height,now=None):
        now=time.monotonic() if now is None else now
        self.advance(now)
        width=max(1,min(width,self.MAX_WIDTH));height=max(1,min(height,self.MAX_HEIGHT))
        if self.logical>=self.next_switch:self.change(now)
        if self.size!=(width,height):
            self.size=(width,height);self.cached=None;self.previous=None
        if self.cached is not None and self.logical-self.last_render<self.FRAME_INTERVAL:return self.cached
        frame=Frame(width,height)
        # Match the approved poster: an open left half, two forms on the right.
        primary_w=max(1,round(width*.45));primary_h=max(1,round(height*.78))
        base=self.scene.render(primary_w,primary_h,self.logical-self.started+13.)
        ox=width-primary_w;oy=max(0,round(height*.10))
        for y,row in enumerate(base.cells):
            for x,(char,_) in enumerate(row):frame.cells[y+oy][x+ox]=(char,'#244ed7')
        small_w=max(1,round(width*.25));small_h=max(1,round(height*.34))
        overlay=self.overlay.render(small_w,small_h,self.logical-self.started+5.)
        ox=width-small_w;oy=max(0,round(height*.15))
        for y,row in enumerate(overlay.cells):
            for x,(char,_) in enumerate(row):
                if char!=' ':frame.cells[y+oy][x+ox]=(char,'#c96a98')
        age=self.logical-self.started
        if self.previous is not None and age<self.TRANSITION:
            old=self.previous;mix=age/self.TRANSITION;merged=Frame(width,height)
            for y,row in enumerate(frame.cells):
                for x,cell in enumerate(row):
                    threshold=((x*13+y*7)%32)/32
                    merged.cells[y][x]=cell if threshold<=mix else old.cells[y][x]
            frame=merged
        else:self.previous=None
        self.cached=frame;self.last_render=self.logical
        return frame
