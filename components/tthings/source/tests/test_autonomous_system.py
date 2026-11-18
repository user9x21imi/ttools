import unittest
from unittest.mock import patch
from tthings.os_info import logo_catalog,choose_logo,gather_system_data
from tthings.system_fetch import Logo3D,render_system_info,crop_ink
from tthings.effects import Frame

class AutonomousSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=logo_catalog()
    def test_bundled_catalog_has_cross_platform_and_distro_logos(self):
        self.assertGreater(len(self.catalog),500)
        keys=[]
        for system,release,expected in [('Windows',{},'windows'),('Darwin',{},'macos'),('Linux',{'ID':'arch'},'arch'),('Linux',{'ID':'gentoo'},'gentoo'),('Linux',{'ID':'debian'},'debian'),('Linux',{'ID':'steamos'},'steamos')]:
            key,logo=choose_logo(self.catalog,system,release)
            self.assertIn(expected,key.casefold());keys.append(key)
            self.assertTrue(logo['lines'])
        self.assertEqual(len(keys),len(set(keys)))
    def test_unknown_linux_never_falls_back_to_steamos(self):
        key,_=choose_logo(self.catalog,'Linux',{'ID':'unknown-distro'})
        self.assertEqual(key.casefold(),'linux')
    def test_native_data_never_launches_external_programs(self):
        with patch('subprocess.run',side_effect=AssertionError('External program invoked')),patch('subprocess.check_output',side_effect=AssertionError('External program invoked')):
            data=gather_system_data()
        self.assertEqual(data['backend'],'native');self.assertTrue(data['rows'])
    def test_logo_top_aligns_with_title_in_tall_terminal(self):
        data=gather_system_data();renderer=Logo3D(data['logo'])
        for width,height in [(110,34),(140,75)]:
            frame=render_system_info(data,width,height,1,renderer)
            left=[y for y,row in enumerate(frame.cells) if any(ch!=' ' for ch,_ in row[:40])]
            self.assertEqual(min(left),4)
    def test_long_labels_cannot_overlap_value_column(self):
        data=gather_system_data();data['rows']=[('Disk /very-long-mount/path/subvolume','12.0 / 80.0 GiB')]
        frame=render_system_info(data,100,35,0)
        text=frame.plain();self.assertIn('12.0 /',text)
        self.assertNotIn('Disk /very-long-mount/path/subvolume12',text)

if __name__=='__main__':unittest.main()
