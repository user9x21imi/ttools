import unittest
from unittest.mock import patch
from tthings.snapping import snap_point,normalize_rectangles
from tthings.__main__ import main

class SnapTests(unittest.TestCase):
    def test_edges_and_corner(self):
        windows=[[100,100,400,300]]
        self.assertEqual(snap_point(104,108,windows),(100,100))
        self.assertEqual(snap_point(495,200,windows),(500,200))
        self.assertEqual(snap_point(300,390,windows),(300,400))
    def test_free_points_and_faraway_edge_extensions(self):
        windows=[[100,100,400,300]]
        self.assertEqual(snap_point(300,200,windows),(300,200))
        self.assertEqual(snap_point(105,700,windows),(105,700))
    def test_nearest_of_two_windows(self):
        self.assertEqual(snap_point(507,200,[[100,100,400,300],[510,100,200,300]]),(510,200))
    def test_negative_coordinates(self):
        self.assertEqual(snap_point(-905,-95,[[-900,-100,400,300]]),(-900,-100))
    def test_reject_bad_geometry(self):
        self.assertEqual(normalize_rectangles([[0,0,float('nan'),4],[0,0,-1,2],['bad'],[-100,0,100,300]]),[[-100.,0.,100.,300.]])
    @patch('tthings.gui.show')
    def test_launch_modifier_latched_into_gui(self,show):
        self.assertEqual(main(['--region','--snap']),0)
        self.assertTrue(show.call_args.kwargs['snap'])
    @patch('tthings.app.subprocess.Popen')
    def test_hotkey_spawns_snap_mode(self,popen):
        from tthings.app import spawn_window
        spawn_window(True,snap=True)
        self.assertIn('--region',popen.call_args.args[0])
        self.assertIn('--snap',popen.call_args.args[0])

if __name__=='__main__':unittest.main()
