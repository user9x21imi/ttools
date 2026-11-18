import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
if os.name != "nt":
    import fcntl,pty,termios

from ttools import core
from ttools.__main__ import EFFECTS
from ttools.backgrounds import Scene

class CatalogTests(unittest.TestCase):
    def test_relative_unicode_paths_and_argv_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='новая папка ') as folder:
            path = Path(folder)/'apps.local.json'
            path.write_text(json.dumps({'apps':[{'id':'test','command':['./bin/client','a b','$(false)']}]}))
            app = core.read_catalog(path)[0]
            self.assertEqual(app['command'],[str((Path(folder)/'bin/client').resolve()),'a b','$(false)'])

    def test_reimport_refresh_and_merge_by_id(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(core,'CONFIG',Path(folder)/'config'):
            path = Path(folder)/'apps.local.json'
            path.write_text(json.dumps({'apps':[{'id':'test','command':['first']}]}))
            core.add_source(path)
            path.write_text(json.dumps({'apps':[{'id':'test','command':['second']},{'id':'new','command':['third']}]}))
            core.add_source(path)
            self.assertEqual(len(core.sources()),1)
            apps,errors = core.load_apps()
            self.assertFalse(errors)
            self.assertEqual([a['command'][0] for a in apps],['second','third'])
            path.unlink()
            self.assertTrue(core.load_apps()[1])

    def test_managed_catalog_wins_over_legacy_wrappers(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(core,'CONFIG',Path(folder)/'config'):
            root=Path(folder)
            legacy=root/'legacy.json';managed=root/'managed.json'
            legacy.write_text(json.dumps({'apps':[{'id':'tspotify','command':['old-wrapper']}]}))
            managed.write_text(json.dumps({'apps':[{'id':'tspotify','command':['real-managed-binary']}]}))
            core.add_source(legacy)
            with patch.dict(os.environ,{'TTOOLS_CATALOG':str(managed)}):
                self.assertEqual(core.load_apps()[0][0]['command'],['real-managed-binary'])

    def test_shell_string_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'apps.local.json'
            path.write_text('{"apps":[{"id":"bad","command":"sh -c something"}]}')
            with self.assertRaises(ValueError):
                core.read_catalog(path)

    def test_update_comparison(self):
        import io
        response = io.StringIO('{"tag_name":"v1.3.1"}')
        with patch('urllib.request.urlopen',return_value=response):
            self.assertEqual(core.check_update({'repository':'https://github.com/owner/repo','version':'1.3.1'}),'Актуальная версия')
        self.assertEqual(core.check_update({}),'Нет источника обновлений')

    def test_backgrounds_resize(self):
        for name in EFFECTS:
            scene = Scene(name,seed=12)
            for w,h in [(80,24),(64,18),(110,40),(1,1)]:
                for t in [0,1,60]:
                    frame = scene.render(w,h,t)
                    self.assertEqual(len(frame.cells),h)

@unittest.skipIf(os.name == "nt", "POSIX PTY integration; Windows uses native console")
class TerminalTests(unittest.TestCase):
    def test_launch_return_resize_search_and_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = root/'child.py'
            marker = root/'ran'
            child.write_text(f'from pathlib import Path\nprint("CHILD_READY",flush=True)\ninput()\nPath({str(marker)!r}).write_text("done")\n')
            catalog = root/'apps.local.json'
            catalog.write_text(json.dumps({'apps':[{'id':'test','name':'Проверка','command':[sys.executable,str(child)]},{'id':'missing','command':['/no/such/executable']}]}))
            config = root/'ttools'
            config.mkdir()
            (config/'sources.json').write_text(json.dumps([str(catalog)]))
            master,slave = pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0))
            env = dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=folder)
            proc = subprocess.Popen([sys.executable,'-m','ttools','--no-splash'],stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
            os.close(slave)
            output = bytearray()
            def pump(duration):
                until = time.monotonic()+duration
                while time.monotonic()<until:
                    if select.select([master],[],[],.05)[0]:
                        try:
                            output.extend(os.read(master,65536))
                        except OSError:
                            break
            try:
                deadline=time.monotonic()+10
                while 'ПРИЛОЖЕНИЯ'.encode() not in output and time.monotonic()<deadline:pump(.1)
                self.assertIn('ПРИЛОЖЕНИЯ'.encode(),output)
                os.write(master,b'\n')
                deadline=time.monotonic()+5
                while b'CHILD_READY' not in output and time.monotonic()<deadline:pump(.1)
                self.assertIn(b'CHILD_READY',output)
                self.assertNotIn(b']4;',output)  # Never mutate the terminal ANSI palette.
                self.assertIn(b';49m',output)  # Default background preserves window opacity.
                os.write(master,b'\n')
                pump(.5)
                self.assertTrue(marker.exists())
                # Missing executable is reported without handing over the terminal.
                os.write(master,b'j\n')
                pump(.2)
                self.assertIn('Не найдена команда'.encode(),output)
                for h,w in [(12,40),(24,80),(35,120)]:
                    fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',h,w,0,0))
                    proc.send_signal(signal.SIGWINCH)
                    pump(.15)
                os.write(master,'/Пров'.encode())
                pump(.2)
                os.write(master,b'\x1bq')
                pump(.3)
                self.assertEqual(proc.wait(timeout=3),0,output[-1500:])
                self.assertNotIn(b'Traceback',output)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
                os.close(master)

if __name__ == '__main__':
    unittest.main()
