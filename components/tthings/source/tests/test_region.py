import subprocess
import unittest
from unittest.mock import patch
from tthings.region import parse_rectangle,select_desktop_region

class RegionTests(unittest.TestCase):
    def test_negative_screen_coordinates(self):
        self.assertEqual(parse_rectangle('qml: TTHINGS_REGION -900 -30 400 250\n'),(-900,-30,400,250))
    def test_cancel_or_tiny_selection(self):
        self.assertIsNone(parse_rectangle(''))
        self.assertIsNone(parse_rectangle('TTHINGS_REGION 0 0 1 1'))
    @patch('tthings.region.subprocess.Popen')
    @patch('tthings.region.qml_runtime',return_value='/qt/qml')
    def test_system_qt_isolated_from_frozen_libraries(self,runtime,run):
        run.return_value.communicate.return_value=('','TTHINGS_REGION 100 200 600 300');run.return_value.returncode=0;run.return_value.args=[]
        with patch.dict('os.environ',{'LD_LIBRARY_PATH':'/tmp/frozen-libs','LD_LIBRARY_PATH_ORIG':'/system/lib',
                                    'XDG_SESSION_TYPE':'wayland','WAYLAND_DISPLAY':'wayland-0'}):
            self.assertEqual(select_desktop_region(),(100,200,600,300))
        self.assertEqual(run.call_args.args[0][1],'--transparent')
        env=run.call_args.kwargs['env']
        self.assertEqual(env['QT_QPA_PLATFORM'],'wayland')
        self.assertEqual(env['LD_LIBRARY_PATH'],'/system/lib')
        self.assertEqual(env['QT_FORCE_STDERR_LOGGING'],'1')
    @patch('tthings.region.qml_runtime',return_value=None)
    def test_no_opaque_fallback_when_qt_unavailable(self,runtime):
        with self.assertRaisesRegex(RuntimeError,'Qt 6'):
            select_desktop_region()

if __name__=='__main__':unittest.main()
