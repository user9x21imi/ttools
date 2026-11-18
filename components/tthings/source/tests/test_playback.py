import unittest
from tthings.playback import AutoCycle,RepeatHold,canonical_key

class PlaybackTests(unittest.TestCase):
    def test_autoplay_deadline_pause_and_toggle(self):
        auto=AutoCycle(interval=lambda:30)
        auto.toggle(10);self.assertFalse(auto.due(39));self.assertTrue(auto.due(40));self.assertEqual(auto.deadline,70)
        self.assertFalse(auto.due(50,paused=True));self.assertFalse(auto.due(100,paused=True))
        self.assertFalse(auto.due(110));self.assertEqual(auto.deadline,130)
        self.assertTrue(auto.due(130));self.assertFalse(auto.toggle(131));self.assertFalse(auto.due(500))
    def test_hold_once_until_release_gap(self):
        hold=RepeatHold();self.assertTrue(hold.press(0))
        for i in range(1,25):hold.press(i*.1)
        self.assertTrue(hold.due(2.4));self.assertFalse(hold.due(2.5))
        self.assertTrue(hold.press(5));self.assertFalse(hold.due(5.1))
    def test_latin_and_cyrillic_controls(self):
        for key in ['R','r','к','К','Cyrillic_ka']:self.assertEqual(canonical_key(key),'r')
        for key in ['N','n','т','Cyrillic_te']:self.assertEqual(canonical_key(key),'n')

if __name__=='__main__':unittest.main()
