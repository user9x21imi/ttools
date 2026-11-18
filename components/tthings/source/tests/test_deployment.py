import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from tthings.deployment import apply_update,rollback,PrefixLock,InstanceLease,active_instances,digest,choose_artifact

@unittest.skipUnless(sys.platform.startswith('linux'),'First supported managed target is Linux')
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='tthings пакет ');self.base=Path(self.temp.name);self.prefix=self.base/'Мой лаунчер/программы/tthings'
    def tearDown(self):self.temp.cleanup()
    def bundle(self,version):
        directory=self.base/('package-'+version);directory.mkdir(exist_ok=True);artifact=directory/'tthings'
        artifact.write_text("#!/usr/bin/env python3\nimport sys,json\nif '--version' in sys.argv: print("+repr(version)+")\nelse: print(json.dumps([{'id':'clock','kind':'effect','builtin':True}]))\n")
        artifact.chmod(0o755);manifest={'schema_version':1,'app_id':'tthings','version':version,'requires_stop':True,'artifacts':[{'platform':'linux-x86_64','path':'tthings','url':None,'sha256':digest(artifact),'kind':'executable','minimum_glibc':'2.0'}]}
        path=directory/'update.json';path.write_text(json.dumps(manifest));return path
    def test_install_repeat_update_and_manual_rollback(self):
        one=self.bundle('0.0.1');two=self.bundle('0.0.2')
        self.assertEqual(apply_update(one,self.prefix)['status'],'installed')
        self.assertEqual(apply_update(one,self.prefix)['status'],'unchanged')
        self.assertEqual(apply_update(two,self.prefix)['status'],'updated')
        self.assertEqual(rollback(self.prefix)['version'],'0.0.1')
    def test_bad_hash_keeps_old_runtime(self):
        one=self.bundle('0.0.1');two=self.bundle('0.0.2');apply_update(one,self.prefix)
        old=digest(self.prefix/'bin/tthings');(two.parent/'tthings').write_text('tampered')
        with self.assertRaisesRegex(RuntimeError,'SHA-256'):apply_update(two,self.prefix)
        self.assertEqual(digest(self.prefix/'bin/tthings'),old)
    def test_failed_activation_restores_old_file_and_metadata(self):
        one=self.bundle('0.0.1');two=self.bundle('0.0.2');apply_update(one,self.prefix);old=digest(self.prefix/'bin/tthings')
        from tthings import deployment
        original=deployment.probe
        def fail_after_move(path,kind,version):
            if Path(path)==self.prefix/'bin/tthings':raise RuntimeError('simulated post-activation failure')
            return original(path,kind,version)
        with patch('tthings.deployment.probe',side_effect=fail_after_move):
            with self.assertRaisesRegex(RuntimeError,'post-activation'):apply_update(two,self.prefix)
        self.assertEqual(digest(self.prefix/'bin/tthings'),old)
        self.assertEqual(json.loads((self.prefix/'.tthings/install.json').read_text())['version'],'0.0.1')
    def test_concurrent_updates_are_rejected(self):
        manifest=self.bundle('0.0.1')
        with PrefixLock(self.prefix):
            with self.assertRaisesRegex(RuntimeError,'занят'):apply_update(manifest,self.prefix)
    def test_live_shared_lease_blocks_update(self):
        one=self.bundle('0.0.1');two=self.bundle('0.0.2');apply_update(one,self.prefix)
        lease=InstanceLease(self.prefix);lease.start()
        try:
            self.assertTrue(active_instances(self.prefix))
            with self.assertRaisesRegex(RuntimeError,'занят'):apply_update(two,self.prefix)
        finally:lease.close()
        self.assertFalse(active_instances(self.prefix));self.assertEqual(apply_update(two,self.prefix)['status'],'updated')
    def test_source_fallback_on_older_glibc(self):
        manifest={'artifacts':[{'platform':'linux-x86_64','minimum_glibc':'2.42'},{'platform':'python-source','kind':'zipapp'}]}
        with patch('tthings.deployment.platform.libc_ver',return_value=('glibc','2.35')):self.assertEqual(choose_artifact(manifest)['platform'],'python-source')

if __name__=='__main__':unittest.main()
