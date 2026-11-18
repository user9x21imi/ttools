import datetime
import unittest
from tthings.metrics import Sampler
from tthings.system_ui import render_monitor
from tthings.dashboard import render_calendar,render_world_clocks

class DashboardTests(unittest.TestCase):
    def test_resize_real_sample(self):
        sampler=Sampler();sampler.sample();sample=sampler.sample()
        for width,height in [(24,10),(60,24),(80,28),(120,40),(180,55)]:
            for kind in ('performance','network','disk-io','disk-space','sensors','processes'):
                frame,_=render_monitor(kind,sample,width,height)
                self.assertEqual((frame.w,frame.h),(width,height))
            for frame in (render_calendar(width,height,2026,11,datetime.date(2026,11,18)),render_world_clocks(width,height)):
                self.assertEqual((frame.w,frame.h),(width,height))
    def test_no_fabricated_history(self):
        from tthings.effects import Frame
        from tthings.dashboard import plot
        a=Frame(30,10);b=Frame(30,10)
        plot(a,0,0,30,10,[],'#ffffff');plot(b,0,0,30,10,[None,None],'#ffffff')
        self.assertEqual(a.plain(),b.plain())
