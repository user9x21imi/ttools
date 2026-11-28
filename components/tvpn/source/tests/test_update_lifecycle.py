"""Lifecycle guards and file rollback remain testable without system setup."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tvpn_updater_lifecycle_test',SOURCE/'updater.py')
updater=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=updater
spec.loader.exec_module(updater)


class LifecycleTests(unittest.TestCase):
    def test_active_lifecycle_lock_blocks_a_second_owner(self):
        with tempfile.TemporaryDirectory(prefix='tvpn-lock-test-') as folder:
            root=Path(folder)
            with updater.lifecycle(root,'ui'):
                self.assertTrue(updater.lifecycle_status(root)['running'])
                with self.assertRaises(updater.UpdateError):
                    with updater.lifecycle(root,'update'):
                        pass

    def test_failed_cleanup_refuses_update_before_download(self):
        with tempfile.TemporaryDirectory(prefix='tvpn-cleanup-test-') as folder:
            root=Path(folder)
            (root/'VERSION').write_text('1.3.1',encoding='utf-8')
            (root/'.cleanup.json').write_text(json.dumps({'cleanup':'failed'}),encoding='utf-8')
            calls=[]
            def unexpected_download(*args,**kwargs):calls.append(args)
            update=updater.Update('1.4.0','https://raw.githubusercontent.com/user9x21imi/tvpn/main/assets/updates/1.4.0.zip','0'*64,1)
            with self.assertRaises(updater.UpdateError):
                updater.apply(update,root,fetch=unexpected_download)
            self.assertEqual(calls,[])

    def test_file_replace_rolls_back_after_finalize_failure(self):
        with tempfile.TemporaryDirectory(prefix='tvpn-rollback-test-') as folder:
            root=Path(folder)/'install';stage=Path(folder)/'stage'
            root.mkdir();stage.mkdir()
            (root/'VERSION').write_text('old',encoding='utf-8')
            (stage/'VERSION').write_text('new',encoding='utf-8')
            (stage/'new.py').write_text('candidate',encoding='utf-8')
            def fail():raise RuntimeError('synthetic helper setup failure')
            with self.assertRaisesRegex(RuntimeError,'synthetic helper setup failure'):
                updater.replace_files(root,stage,finalize=fail)
            self.assertEqual((root/'VERSION').read_text(encoding='utf-8'),'old')
            self.assertFalse((root/'new.py').exists())


if __name__=='__main__':unittest.main()
