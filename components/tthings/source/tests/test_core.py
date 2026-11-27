import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tthings.catalog import BUILTINS,ENTRIES,executable,search
from tthings.effects import Scene,Frame
from tthings.settings import read,save

class RenderTests(unittest.TestCase):
    def test_every_effect_at_tiny_and_normal_sizes_and_after_resize(self):
        for entry in BUILTINS:
            scene=Scene(entry.id,seed=42)
            for w,h in [(1,1),(4,2),(20,8),(80,24),(130,40),(12,5)]:
                for t in [0,.2,8,30]:
                    with self.subTest(effect=entry.id,size=(w,h),time=t):
                        frame=scene.render(w,h,t)
                        self.assertEqual(len(frame.cells),h)
                        self.assertTrue(all(len(row)==w for row in frame.cells))
                        self.assertTrue(all(len(ch)==1 and len(color)==7 for row in frame.cells for ch,color in row))
    def test_braille_bit_layout_and_clipping(self):
        f=Frame(1,1)
        f.braille([(0,0,'#ffffff'),(1,3,'#ffffff'),(-1,0,'#ffffff'),(2,0,'#ffffff')])
        self.assertEqual(f.cells[0][0][0],chr(0x2800|1|128))
    def test_life_blinker(self):
        scene=Scene('life');scene.render(8,8,0)
        scene.state['cells']={(2,3),(3,3),(4,3)}
        scene.render(8,8,1)
        self.assertEqual(scene.state['cells'],{(3,2),(3,3),(3,4)})
    def test_bonsai_growth(self):
        early=Scene('bonsai').render(80,24,0).plain()
        late=Scene('bonsai').render(80,24,15).plain()
        self.assertGreater(sum(c!=' ' and c!='\n' for c in late),sum(c!=' ' and c!='\n' for c in early))

class CatalogTests(unittest.TestCase):
    def test_unique_ids_and_search(self):
        self.assertEqual(len({e.id for e in ENTRIES}),len(ENTRIES))
        self.assertIn('lava',[e.id for e in search('ЛАВОВАЯ')])
        self.assertTrue(all(e.builtin for e in search(mode='builtin')))
        self.assertTrue(all(not e.builtin for e in search(mode='external')))
        self.assertEqual(search('no-such-effect'),[])
    def test_portable_tool_path(self):
        entry=next(e for e in ENTRIES if e.id=='lavat')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'lavat/bin/lavat';path.parent.mkdir(parents=True);path.write_text('');path.chmod(0o755)
            with patch.dict(os.environ,{'TTHINGS_TOOLS':temp}):self.assertEqual(executable(entry),str(path))

class SettingsTests(unittest.TestCase):
    def test_roundtrip_and_corruption(self):
        from tthings.settings import config_path
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'XDG_CONFIG_HOME':temp,'APPDATA':temp}):
            self.assertEqual(read(),{})
            save({'favorites':['lava'],'palette':1})
            self.assertEqual(read()['favorites'],['lava'])
            config_path().write_text('invalid')
            self.assertEqual(read(),{})

class CommandTests(unittest.TestCase):
    def test_json_catalog(self):
        p=subprocess.run([sys.executable,'-m','tthings','--list','--json'],capture_output=True,text=True,check=True,encoding='utf-8',errors='replace')
        self.assertEqual(len(json.loads(p.stdout)),len(ENTRIES))
    def test_noninteractive_is_actionable(self):
        p=subprocess.run([sys.executable,'-m','tthings'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('--snapshot',p.stderr)

if __name__=='__main__':unittest.main()
