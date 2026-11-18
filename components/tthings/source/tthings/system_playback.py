"""Random tool navigation that survives view cleanup and tool changes."""
import random
import time
from .playback import AutoCycle,RepeatHold
from .system_utilities import UtilitySuite

class SystemPlayback:
    def __init__(self,interval=None,choose=None):
        self.auto=AutoCycle(interval);self.hold=RepeatHold();self.choose=choose or random.choice
        self.palette=None;self.utilities=UtilitySuite();self.started=time.monotonic()
    def random(self,current,ids,now):
        self.auto.reset(now)
        choices=[key for key in ids if key!=current]
        return self.choose(choices) if choices else current
    def poll(self,current,ids,now):
        self.utilities.update(now)
        if self.hold.due(now):self.auto.toggle(now)
        if self.auto.due(now):return self.random(current,ids,now)
    def key(self,key,current,ids,now):
        if key=='r':
            if self.hold.press(now):return self.random(current,ids,now)
        elif key=='a':self.auto.toggle(now)
        elif key=='n':self.auto.reset(now);return ids[(ids.index(current)+1)%len(ids)]
    def status(self,now):
        return f'АВТО {self.auto.remaining(now)}с' if self.auto.enabled else 'R 2с → авто'
