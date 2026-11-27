import sys,unittest,tempfile,zipfile,json,io
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'source'))
import manage,vtcurses as vt
import chat_transition as windows_transition
class Core(unittest.TestCase):
    def test_four_stage_transition_uses_all_states(self):
        count=windows_transition.CHAT_TRANSITION_STATE_COUNT
        states=[windows_transition.chat_transition_state(windows_transition.CHAT_TRANSITION_SECONDS*(index+.1)/count) for index in range(count)]
        self.assertEqual(count,4)
        self.assertEqual(states,list(range(4)))
        self.assertEqual(len(windows_transition.CHAT_TRANSITION_GLYPHS),4)
    def test_wheel_traversal(self):
        with tempfile.TemporaryDirectory(prefix='Telegram тест ') as d:
            root=Path(d);wheel=root/'bad.whl'
            with zipfile.ZipFile(wheel,'w') as z:z.writestr('../outside','x')
            with self.assertRaises(RuntimeError):manage.extract_wheel(wheel,root/'packages')
    def test_windows_payload_extracts(self):
        with tempfile.TemporaryDirectory(prefix='Telegram тест ') as d:
            root=Path(d)
            wheels=sorted((ROOT/'wheels').glob('*.whl'))
            self.assertTrue(wheels,f'checked-in Windows wheelhouse is missing or empty: {ROOT / "wheels"}')
            for wheel in wheels:manage.extract_wheel(wheel,root)
            self.assertTrue((root/'tg/__init__.py').is_file());self.assertTrue((root/'telegram/_native_tdjson.py').is_file())
            self.assertTrue(list(root.rglob('*.pyd')));self.assertTrue(list(root.rglob('*.exe')))
    def test_checked_in_payload_is_complete(self):
        manifest=manage.read(ROOT/'files.json')
        missing=[name for name in manifest if not (ROOT/name).is_file()]
        self.assertFalse(missing,'checked-in Windows payload is incomplete; missing manifest files: '+', '.join(missing))
        try:manage.verify(ROOT)
        except RuntimeError as error:self.fail(f'checked-in Windows payload failed its SHA-256 manifest: {error}')
    def test_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'source.py';p.write_text('original');manage.write(root/'files.json',{'source.py':manage.digest(p)})
            manage.verify(root);p.write_text('changed')
            with self.assertRaises(RuntimeError):manage.verify(root)
    def test_pointer_rollback_paths(self):
        with tempfile.TemporaryDirectory(prefix='Telegram тест ') as d:
            root=Path(d);(root/'versions/v1').mkdir(parents=True);manage.write(root/'current.json',{'version':'v1'});self.assertEqual(manage.current(root),(root/'versions/v1').resolve())
            manage.write(root/'current.json',{'version':'../../outside'})
            with self.assertRaises(RuntimeError):manage.current(root)
    def test_missing_pointer_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError) as error:manage.current(Path(d))
            self.assertIn('install.cmd',str(error.exception))
    def test_bundle_prefix_fallback_installs_on_demand(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';installed=root/'prefix'
            (bundle/'bootstrap').mkdir(parents=True);(bundle/'bootstrap/python.exe').write_bytes(b'');(bundle/'wheels').mkdir()
            calls=[]
            with patch.object(manage,'BUNDLE',bundle),patch.object(manage,'default_prefix',lambda:installed),patch.object(manage,'install',side_effect=lambda prefix:calls.append(prefix)):
                self.assertEqual(manage.recover_bundle_prefix(bundle,'version'),installed);self.assertEqual(calls,[installed])
                manage.write(installed/'current.json',{'version':'v1'})
                self.assertEqual(manage.recover_bundle_prefix(bundle,'launch'),installed);self.assertEqual(len(calls),1)
                self.assertEqual(manage.recover_bundle_prefix(bundle,'install'),bundle)
                self.assertEqual(manage.recover_bundle_prefix(installed,'version'),installed)
    def test_dirty_refresh_does_not_erase_images(self):
        screen=vt.newwin(4,20);out=io.StringIO()
        with patch('sys.stdout',out):
            screen.addstr(0,0,'Telegram');screen.refresh();size=len(out.getvalue());screen.refresh();self.assertEqual(size,len(out.getvalue()))
            screen.addstr(3,0,'Draft');screen.refresh()
        self.assertNotIn('\x1b[1;1H',out.getvalue()[size:])
    def test_mouse_and_key_sequences(self):
        vt._size=vt._dimensions();vt._keys.clear()
        vt._keys.extend('\x1b[A');self.assertEqual(vt._get_key(0),vt.KEY_UP)
        vt._keys.extend('\x1b[<0;20;10M');self.assertEqual(vt._get_key(0),vt.KEY_MOUSE);self.assertEqual(vt.getmouse()[1:3],(19,9))
        vt._keys.extend('\x1b[6;20;10t');self.assertEqual(vt._get_key(0),vt.KEY_RESIZE);self.assertEqual(vt.get_cell_size(),(10,20))
    def test_find_windows_terminal_prefers_path_then_app_alias(self):
        with patch.object(manage.shutil,'which',return_value='C:/PATH/wt.exe'):
            self.assertEqual(manage.find_windows_terminal(),'C:/PATH/wt.exe')
        with tempfile.TemporaryDirectory(prefix='Telegram тест ') as directory:
            alias=Path(directory)/'Microsoft/WindowsApps/wt.exe';alias.parent.mkdir(parents=True);alias.write_bytes(b'')
            with patch.object(manage.shutil,'which',return_value=None),patch.dict(manage.os.environ,{'LOCALAPPDATA':directory}):
                self.assertEqual(manage.find_windows_terminal(),str(alias))
        with patch.object(manage.shutil,'which',return_value=None),patch.dict(manage.os.environ,{'LOCALAPPDATA':''}):
            self.assertIsNone(manage.find_windows_terminal())
if __name__=='__main__':unittest.main()
