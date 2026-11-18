import unittest
from unittest.mock import patch
from ttools.backgrounds import Background
from ttools.__main__ import UI
class BackgroundTests(unittest.TestCase):
    def test_pause_preserves_frame_and_resume_advances_time(self):
        bg=Background(seed=4,now=0)
        frame=bg.render(80,24,1)
        bg.toggle(1)
        self.assertIs(bg.render(80,24,600),frame)
        self.assertEqual(bg.logical,1)
        bg.toggle(600)
        self.assertIsNot(bg.render(80,24,601),frame)
        self.assertEqual(bg.logical,2)
    def test_rate_limit_resize_and_two_layer_palette(self):
        bg=Background(seed=1,now=0)
        frame=bg.render(80,24,1)
        self.assertIs(bg.render(80,24,1.02),frame)
        self.assertEqual({c for row in frame.cells for ch,c in row if ch!=' '},{'#244ed7','#c96a98'})
        large=bg.render(9999,9999,2)
        self.assertEqual((large.w,large.h),(180,72))
        tiny=bg.render(0,0,3)
        self.assertEqual((tiny.w,tiny.h),(1,1))
    def test_manual_switch_while_paused_and_transition_resize(self):
        bg=Background(seed=8,now=0,motion=False)
        old=bg.effect;bg.render(80,24,0);bg.change(3)
        self.assertNotEqual(bg.effect,old)
        frame=bg.render(80,24,50)
        self.assertIs(bg.render(80,24,100),frame)
        bg.toggle(100);bg.change(101);bg.render(10,10,101.1)
        self.assertEqual(bg.size,(10,10))
    def test_low_power_caps_area_and_frame_rate(self):
        bg=Background(seed=1,now=0,low_power=True)
        frame=bg.render(300,100,0)
        self.assertEqual((frame.w,frame.h),(96,32))
        self.assertIs(bg.render(300,100,.24),frame)
        self.assertIsNot(bg.render(300,100,.26),frame)

    def test_unchanged_ui_cells_are_not_written_again(self):
        class Screen:
            def __init__(self):self.writes=[]
            def addnstr(self,*args):self.writes.append(args)
            def refresh(self):pass
        ui=UI.__new__(UI);ui.s=Screen();ui._pending={(0,0):('A',1,False)}
        with patch('curses.color_pair',return_value=1):
            ui.flush();self.assertEqual(len(ui.s.writes),1)
            ui.flush();self.assertEqual(len(ui.s.writes),1)
            ui._pending={};ui.flush()
            self.assertEqual(ui.s.writes[-1][2],' ')
if __name__=='__main__':unittest.main()
