import sys,unittest,tempfile,zipfile,json,io
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'source'))
import manage,vtcurses as vt
class Core(unittest.TestCase):
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
if __name__=='__main__':unittest.main()
