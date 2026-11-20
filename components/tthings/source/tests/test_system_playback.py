import unittest
from tthings.system_playback import SystemPlayback
from tthings.system_utilities import UtilitySuite,calculate
from tthings.system_ui import font_control

class SystemsPlaybackTests(unittest.TestCase):
    def test_single_random_and_hold_survives_switch_then_autocycles(self):
        s=SystemPlayback(interval=lambda:30,choose=lambda choices:choices[0]);ids=['calendar','epoch','performance']
        current=s.key('r','calendar',ids,0);self.assertEqual(current,'epoch')
        for i in range(1,22):
            self.assertIsNone(s.key('r',current,ids,i*.1));self.assertIsNone(s.poll(current,ids,i*.1))
        self.assertTrue(s.auto.enabled);self.assertGreaterEqual(s.auto.deadline,32)
        self.assertIsNone(s.poll(current,ids,31));self.assertNotEqual(s.poll(current,ids,32.2),current)
        self.assertTrue(s.auto.enabled)
    def test_next_toggle_and_countdown_persist(self):
        s=SystemPlayback(interval=lambda:30);self.assertEqual(s.key('n','x',['x','y'],1),'y')
        s.key('a','x',['x','y'],2);self.assertTrue(s.auto.enabled)
        s.utilities.key('countdown',' ',10);s.poll('x',['x','y'],20)
        self.assertEqual(s.utilities.timer.value(20),290)
        s.key('a','x',['x','y'],21);self.assertFalse(s.auto.enabled)
    def test_controls_only_for_visible_features(self):
        for kind in ('processes','journals','date-progress','calculator','color-lab'):
            self.assertIsNone(font_control(kind,100,40))
        self.assertEqual(font_control('performance',100,40),'шрифт цифр')
        self.assertIsNone(font_control('performance',30,12))
    def test_pomodoro_tracks_elapsed_rounds_and_timer_finishes(self):
        u=UtilitySuite();u.key('pomodoro',' ',0);u.update(1510)
        self.assertFalse(u.focus);self.assertEqual(u.rounds,1);self.assertEqual(u.pomodoro.value(1510),290)
        u.key('countdown',' ',0);u.update(305);self.assertEqual(u.timer.value(305),0);self.assertIsNone(u.timer.deadline)
    def test_calculator_has_no_code_execution_or_unbounded_powers(self):
        self.assertEqual(calculate('sqrt(81)+2*(3+4)'),23)
        for text in ["__import__('os')",'2**999999','(1).__class__','[1,2]', 'sqrt(-1)']:
            with self.assertRaises((ValueError,SyntaxError)):calculate(text)
