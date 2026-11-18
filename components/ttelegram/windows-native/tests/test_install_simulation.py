"""Test offline installation transactions on POSIX; Windows execution is stubbed."""
import unittest,tempfile,shutil,sys,types,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import manage
class Install(unittest.TestCase):
    def test_install_reinstall_update_rollback_and_failure(self):
        with tempfile.TemporaryDirectory(prefix='Telegram установка ') as directory:
            base=Path(directory);bundle=base/'bundle';prefix=base/'Лаунчер с пробелами/Telegram'
            bundle.mkdir()
            for name in ('source','bootstrap','wheels'):shutil.copytree(ROOT/name,bundle/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            shutil.copy2(ROOT/'manage.py',bundle/'manage.py')
            def release(version):
                (bundle/'source/VERSION').write_text(version)
                manage.write(bundle/'files.json',{p.relative_to(bundle).as_posix():manage.digest(p) for p in bundle.rglob('*') if p.is_file() and p.name!='files.json'})
            runner=lambda *a,**kw:types.SimpleNamespace(returncode=0,stdout='simulated staged doctor',stderr='')
            with patch.object(manage,'BUNDLE',bundle),patch.object(manage,'sys',types.SimpleNamespace(platform='win32')),patch.object(manage.subprocess,'run',side_effect=runner):
                release('test-v1');manage.install(prefix);manage.install(prefix)
                account=base/'account-data';account.mkdir();(account/'sentinel').write_text('preserve')
                release('test-v2');manage.install(prefix)
                self.assertEqual(manage.read(prefix/'current.json')['version'],'test-v2');self.assertEqual(manage.read(prefix/'previous.json')['version'],'test-v1')
                self.assertTrue((prefix/'versions/test-v2/runtime/Lib/site-packages/telegram/_native_tdjson.py').exists())
                # Doctor failure must leave the previous current installation intact.
                release('broken-v3')
                with patch.object(manage.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout='',stderr='native runtime failed')):
                    with self.assertRaises(RuntimeError):manage.install(prefix)
                self.assertEqual(manage.read(prefix/'current.json')['version'],'test-v2');self.assertFalse((prefix/'versions/broken-v3').exists())
                self.assertEqual((account/'sentinel').read_text(),'preserve')
                manage.rollback(prefix)
                self.assertEqual(manage.read(prefix/'current.json')['version'],'test-v1')
                self.assertEqual(manage.read(prefix/'previous.json')['version'],'test-v2')
                manage.verify(prefix/'versions/test-v1')
                self.assertEqual((prefix/'versions/test-v1/source/VERSION').read_text(),'test-v1')
if __name__=='__main__':unittest.main()
