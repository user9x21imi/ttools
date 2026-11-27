"""Deterministic TVPN panel tests; no subprocess, network, or system setup."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('riseup_panel_offline_test',SOURCE/'riseup-panel.py')
panel=importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class OfflineBackendFixture:
    """Produce the same event protocol as the backend, entirely in memory."""
    def __init__(self,region):
        self.region=region

    def events(self):
        info=panel.REGIONS[self.region]
        yield f'@RISEUP\tavailability\t{self.region}\t3\tRiseup'
        yield f'@RISEUP\tlocation\t{self.region}\t{info["city"]}\t{info["country"]}'
        yield '@RISEUP\tstate\tconnecting\tPreparing synthetic connection'
        yield f'@RISEUP\tgateway\ttest-{self.region}\t{info["city"]}'
        yield f'@RISEUP\tconnected\t198.51.100.7\t{info["country"]}'


class OfflinePanelTests(unittest.TestCase):
    def test_bundled_version_matches_manifest_and_release_notes(self):
        version=(SOURCE/'VERSION').read_text(encoding='utf-8').strip()
        manifest=json.loads((SOURCE/'update.json').read_text(encoding='utf-8'))
        notes=(SOURCE/'RELEASE_NOTES.md').read_text(encoding='utf-8')
        self.assertRegex(version,r'^\d+\.\d+\.\d+$')
        self.assertEqual(manifest['version'],version)
        self.assertEqual(manifest['app_id'],'tvpn')
        top=next(line for line in notes.splitlines() if line.strip())
        self.assertTrue(top.startswith(f'TVPN {version}'),
                        'RELEASE_NOTES must lead with the section for the bundled version')

    def test_region_selection_and_synthetic_catalog_connection(self):
        model=panel.Model('amsterdam',camera=panel.Camera())
        model.counts={'amsterdam':0,'paris':3}
        choice,requested,message=panel.advance_region_selection(0,panel.curses.KEY_ENTER,model.counts)
        self.assertEqual((choice,requested),(0,None))
        self.assertIn('нет шлюзов',message)

        choice,requested,message=panel.advance_region_selection(0,panel.curses.KEY_DOWN,model.counts)
        self.assertEqual((choice,requested,message),(1,None,None))
        choice,requested,message=panel.advance_region_selection(choice,10,model.counts)
        self.assertEqual((choice,requested,message),(None,'paris',None))
        for event in OfflineBackendFixture(requested).events():model.line(event)
        self.assertEqual(model.counts['paris'],3)
        self.assertEqual(model.selected,'paris')
        self.assertEqual(model.expected,'FR')
        self.assertEqual(model.state,'connected')
        self.assertEqual(model.ip,'198.51.100.7')
        self.assertEqual(model.region,'FR')

    def test_synthetic_interface_statistics_are_deterministic(self):
        model=panel.Model('amsterdam',camera=panel.Camera())
        with tempfile.TemporaryDirectory(prefix='tvpn-stat-fixture-') as folder:
            root=Path(folder)
            (root/'rx_bytes').write_text('100')
            (root/'tx_bytes').write_text('200')
            model.sample(1.0,root)
            (root/'rx_bytes').write_text(str(100+2**20))
            (root/'tx_bytes').write_text(str(200+2*2**20))
            model.sample(2.0,root)
        self.assertAlmostEqual(model.down,1.0)
        self.assertAlmostEqual(model.up,2.0)
        self.assertEqual(model.rx,2**20)
        self.assertEqual(model.tx,2*2**20)
        self.assertEqual(model.history[-1],(2.0,1.0,2.0))

    def test_error_and_cleanup_events_do_not_launch_recovery(self):
        model=panel.Model('paris',camera=panel.Camera())
        model.line('@RISEUP\tconnected\t198.51.100.8\tFR')
        self.assertEqual(model.state,'connected')
        model.line('@RISEUP\tstate\terror\tSynthetic backend error')
        model.line('@RISEUP\tcleanup\tok')
        self.assertEqual(model.state,'error')
        self.assertEqual(model.ip,'—')
        self.assertTrue(model.cleanup)

    def test_camera_selects_region_without_terminal_or_backend(self):
        camera=panel.Camera()
        target=panel.REGIONS['seattle']
        camera.select('seattle',target['lat'],target['lon'])
        self.assertEqual(camera.target,(target['lat'],target['lon']))
        camera.tick(camera.last+.15)
        self.assertNotEqual(camera.latitude,18.)
        camera.scale(1.12)
        self.assertGreater(camera.zoom,1.)

    def test_reduced_motion_snaps_focus_and_disables_spin(self):
        camera=panel.Camera(reduced_motion=True)
        target=panel.REGIONS['paris']
        camera.select('paris',target['lat'],target['lon'])
        self.assertAlmostEqual(camera.latitude,target['lat'])
        self.assertAlmostEqual(camera.longitude,target['lon'])
        self.assertIsNone(camera.target)
        camera.toggle()
        self.assertFalse(camera.spinning)

    def test_camera_uses_short_turn_across_date_line_and_redirects(self):
        camera=panel.Camera()
        camera.latitude=0.
        camera.longitude=179.
        camera.focus(0.,-179.)
        camera.tick(camera.last+.1)
        self.assertGreater(abs(camera.longitude),170.)
        camera.select('paris',panel.REGIONS['paris']['lat'],panel.REGIONS['paris']['lon'])
        camera.select('seattle',panel.REGIONS['seattle']['lat'],panel.REGIONS['seattle']['lon'])
        self.assertEqual(camera.region,'seattle')
        self.assertEqual(camera.target,(panel.REGIONS['seattle']['lat'],panel.REGIONS['seattle']['lon']))

    def test_graph_uses_oldest_and_newest_buckets(self):
        bars,_=panel.graph([(0.0,1.0,0.0),(59.0,0.0,2.0)],2,60)
        self.assertEqual(bars[0],'▁')
        self.assertEqual(bars[-1],'█')


if __name__=='__main__':unittest.main()
