import unittest
from tthings.catalog import BUILTINS
from tthings.effects import Scene
from tthings.gallery_effects import REGISTRY

class GalleryTests(unittest.TestCase):
    def test_all_new_scenes_are_nonempty_animate_and_are_distinct(self):
        seen=set()
        for key,*_ in REGISTRY:
            with self.subTest(effect=key):
                scene=Scene(key,42);a=scene.render(100,32,0);b=scene.render(100,32,7)
                self.assertGreater(sum(ch!=' ' for row in a.cells for ch,c in row),30)
                self.assertNotEqual(a.cells,b.cells)
                signature=a.plain();self.assertNotIn(signature,seen);seen.add(signature)
    def test_large_raster_resize_preserves_bounds(self):
        for key in ('shadebobs','fbm_clouds','voronoi_edges','rotozoom'):
            frame=Scene(key,42).render(300,140,5)
            self.assertEqual(len(frame.cells),140);self.assertTrue(all(len(row)==300 for row in frame.cells))
