"""Shared slideshow clock and keyboard normalization."""
import random

KEYS={'а':'f','cyrillic_a':'f','ф':'a','cyrillic_ef':'a','к':'r','т':'n','з':'p','й':'q','р':'h','д':'l','cyrillic_ka':'r','cyrillic_te':'n','cyrillic_ze':'p','cyrillic_shorti':'q','cyrillic_er':'h','cyrillic_de':'l'}
def canonical_key(value):
    value=value.casefold()
    return KEYS.get(value,value)

class AutoCycle:
    def __init__(self,interval=None):self.enabled=False;self.deadline=None;self.paused_at=None;self.interval=interval or (lambda:random.uniform(30,120))
    def toggle(self,now):
        self.enabled=not self.enabled;self.paused_at=None
        self.deadline=now+self.interval() if self.enabled else None
        return self.enabled
    def reset(self,now):
        if self.enabled:self.deadline=now+self.interval();self.paused_at=None
    def due(self,now,paused=False):
        if not self.enabled:return False
        if paused:
            if self.paused_at is None:self.paused_at=now
            return False
        if self.paused_at is not None:self.deadline+=now-self.paused_at;self.paused_at=None
        if now>=self.deadline:self.reset(now);return True
        return False
    def remaining(self,now):
        return max(0,int(self.deadline-(self.paused_at if self.paused_at is not None else now))) if self.enabled else None

class RepeatHold:
    """Terminal input has no key-up events: infer a hold from sustained repeats."""
    def __init__(self):self.started=None;self.last=None;self.count=0;self.toggled=False
    def press(self,now):
        fresh=self.last is None or now-self.last>.9
        if fresh:self.started=now;self.count=0;self.toggled=False
        self.last=now;self.count+=1
        return fresh
    def due(self,now):
        if self.last is None or now-self.last>.9:return False
        if not self.toggled and self.count>=3 and now-self.started>=2:self.toggled=True;return True
        return False
