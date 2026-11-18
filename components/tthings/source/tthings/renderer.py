"""Stable, MIT-licensed background renderer API v1. No terminal/window ownership."""
import math
import time
from .catalog import BUILTINS
from .effects import Scene,Frame

API_VERSION=1

def available_effects():return [{'id':e.id,'title':e.title,'category':e.category} for e in BUILTINS]

class BackgroundRenderer:
    def __init__(self,effect_id,width,height,seed=None,brightness=.18,max_fps=12):
        if effect_id not in {e.id for e in BUILTINS}:raise ValueError('Unknown effect')
        if not math.isfinite(brightness) or not 0<=brightness<=1:raise ValueError('brightness must be 0..1')
        if not math.isfinite(max_fps) or not 1<=max_fps<=60:raise ValueError('max_fps must be 1..60')
        self.scene=Scene(effect_id,seed);self.brightness=brightness;self.max_fps=max_fps;self.started=None;self.last=None;self.cached=None
        self.resize(width,height)
    def resize(self,width,height):
        self.width=max(1,min(300,int(width)));self.height=max(1,min(140,int(height)));self.cached=None;self.last=None
    def render(self,elapsed):
        if not math.isfinite(elapsed):raise ValueError('elapsed must be finite')
        source=self.scene.render(self.width,self.height,max(0,elapsed));result=Frame(self.width,self.height);colors={}
        for y,row in enumerate(source.cells):
            for x,(char,color) in enumerate(row):
                if color not in colors:colors[color]='#%02x%02x%02x'%tuple(int(int(color[i:i+2],16)*self.brightness) for i in (1,3,5))
                result.cells[y][x]=(char,colors[color])
        return result
    def next_frame(self,now=None):
        now=time.monotonic() if now is None else now
        if self.started is None:self.started=now
        if self.cached is None or self.last is None or now-self.last>=1/self.max_fps:
            self.cached=self.render(now-self.started);self.last=now
        return self.cached

def create_renderer(effect_id,width,height,**options):return BackgroundRenderer(effect_id,width,height,**options)
