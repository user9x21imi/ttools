import unittest
from tthings.renderer import API_VERSION,create_renderer,available_effects

class RendererAPITests(unittest.TestCase):
    def test_dim_frame_throttle_and_resize(self):
        renderer=create_renderer('clock',70,20,brightness=.1,max_fps=10)
        one=renderer.next_frame(0);self.assertIs(one,renderer.next_frame(.01))
        self.assertIsNot(one,renderer.next_frame(.2))
        self.assertLessEqual(max(int(c[i:i+2],16) for row in one.cells for ch,c in row for i in (1,3,5)),25)
        renderer.resize(20,8);frame=renderer.next_frame(.21);self.assertEqual((frame.w,frame.h),(20,8))
        self.assertEqual(API_VERSION,1);self.assertTrue(any(e['id']=='clock' for e in available_effects()))

if __name__=='__main__':unittest.main()
