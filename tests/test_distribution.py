import hashlib
import json
import os
from pathlib import Path
import stat
import signal
import shutil
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ttools import distribution as d
from ttools import suite


def fixture(root,version='9.0.0'):
    (root/'components').mkdir(parents=True)
    (root/'components/versions.json').write_text(json.dumps({a:'1.0.0' for a in suite.APP_IDS}))
    (root/'marker.txt').write_text(version)
    files={p.relative_to(root).as_posix():d.digest(p) for p in root.rglob('*') if p.is_file()}
    value={'schema_version':1,'app_id':'ttools','version':version,'platform':d.platform_id(),'files':files}
    (root/'bundle.json').write_text(json.dumps(value))
    return root

class DistributionTests(unittest.TestCase):
    def test_platform_architecture_mapping(self):
        self.assertEqual(d.platform_id('Windows','AMD64'),'windows-x86_64')
        self.assertEqual(d.platform_id('Darwin','arm64'),'macos-arm64')
        self.assertEqual(d.platform_id('Linux','x86_64'),'linux-x86_64')
        with self.assertRaises(ValueError):d.platform_id('Plan9','mips')

    def test_stable_release_sorts_after_its_preview(self):
        self.assertGreater(d.version_key('1.1.0'),d.version_key('1.1.0-preview.1'))
        self.assertGreater(d.version_key('1.2.0-preview.1'),d.version_key('1.1.0'))
        with self.assertRaises(ValueError):d.version_key('../../new')

    def test_archive_traversal_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('../outside','/absolute','C:/Windows/file','folder\\bad'):
                archive=root/'unsafe.zip'
                with zipfile.ZipFile(archive,'w') as package:
                    member=zipfile.ZipInfo(name)
                    member.filename=member.orig_filename=name
                    package.writestr(member,b'no')
                with self.assertRaises(ValueError):d.extract_zip(archive,root/'out')
            with zipfile.ZipFile(root/'link.zip','w') as package:
                info=zipfile.ZipInfo('link');info.external_attr=(stat.S_IFLNK|0o777)<<16
                package.writestr(info,'../outside')
            with self.assertRaises(ValueError):d.extract_zip(root/'link.zip',root/'out')
            self.assertFalse((root/'outside').exists())

    def test_manifest_rejects_modified_or_unlisted_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=fixture(Path(tmp))
            d.verify_bundle(root)
            (root/'marker.txt').write_text('tampered')
            with self.assertRaises(ValueError):d.verify_bundle(root)
            (root/'marker.txt').write_text('9.0.0')
            (root/'unexpected.py').write_text('print("bad")')
            with self.assertRaises(ValueError):d.verify_bundle(root)

    def test_lock_excludes_running_app_and_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)
            with d.locked(prefix):
                with self.assertRaises(RuntimeError):
                    with d.locked(prefix):pass
            with d.locked(prefix):pass

    def test_no_false_full_install_on_windows_or_macos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=fixture(Path(tmp))
            for target in ('windows-x86_64','macos-arm64','macos-x86_64'):
                with self.assertRaises(RuntimeError):suite.plan(root,target,suite.APP_IDS)
                value=suite.plan(root,target,suite.APP_IDS,True)
                self.assertFalse(value['complete'])
                self.assertEqual(value['unsupported'],['ttelegram'])
                self.assertNotIn('ttelegram',value['install'])

    def test_failed_install_keeps_previous_state_and_releases_lock(self):
        with tempfile.TemporaryDirectory(prefix='ttools Юникод ') as tmp:
            root=Path(tmp);bundle=fixture(root/'bundle');prefix=root/'prefix'
            old={'version':'8.0.0','release':str(root/'previous')}
            d.atomic_json(prefix/'state.json',old)
            with patch.object(suite,'linux_prerequisites'),patch.object(suite,'create_venv',return_value=Path('/test/python')),patch.object(suite,'install_pip'),patch.object(suite,'install_component',side_effect=RuntimeError('broken package')):
                with self.assertRaisesRegex(RuntimeError,'broken package'):
                    suite.install(bundle,prefix,selected=['tthings'],shortcuts=False)
            self.assertEqual(json.loads((prefix/'state.json').read_text(encoding='utf-8')),old)
            self.assertEqual(list((prefix/'releases').iterdir()),[])
            with d.locked(prefix):pass

    def test_suite_refuses_downgrading_a_newer_native_vpn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=fixture(root/'bundle');prefix=root/'prefix';old_release=root/'previous'
            vpn=old_release/'apps/tvpn';vpn.mkdir(parents=True)
            (vpn/'VERSION').write_text('2.0.0')
            old={'version':'8.0.0','release':str(old_release)}
            d.atomic_json(prefix/'state.json',old)
            with patch.object(suite,'linux_prerequisites'),patch.object(suite,'stop_previous_background_apps') as stop:
                with self.assertRaisesRegex(RuntimeError,'refusing to downgrade'):
                    suite.install(bundle,prefix,selected=['tvpn'],shortcuts=False)
                stop.assert_not_called()
            self.assertEqual(json.loads((prefix/'state.json').read_text(encoding='utf-8')),old)

    @unittest.skipIf(os.name=='nt','The fixture deliberately bypasses launcher dependency installation')
    def test_success_repeat_install_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='Путь с пробелами ') as tmp:
            root=Path(tmp);first=fixture(root/'first','8.0.0');second=fixture(root/'second','9.0.0');prefix=root/'prefix'
            def fake(app,release,defer_system=False):return ['/test/command','a b'],{}
            with patch.object(suite,'linux_prerequisites'),patch.object(suite,'install_component',side_effect=fake) as install:
                state=suite.install(first,prefix,selected=['tthings'],shortcuts=False)
                suite.install(first,prefix,selected=['tthings'],shortcuts=False)
                self.assertEqual(install.call_count,1)
                suite.install(second,prefix,selected=['tthings'],shortcuts=False)
                suite.rollback(prefix)
                self.assertEqual(json.loads((prefix/'state.json').read_text(encoding='utf-8'))['release'],state['release'])

    def test_bad_download_hash_does_not_invoke_new_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)
            d.atomic_json(prefix/'state.json',{'version':'1.0.0','platform':d.platform_id(),'options':{}})
            remote={'schema_version':1,'app_id':'ttools','version':'2.0.0','artifacts':[{'platform':d.platform_id(),'url':'https://example.com/real.zip','sha256':'0'*64}]}
            def fake_fetch(url,path,*args):Path(path).write_bytes(b'tampered')
            with patch.object(suite,'release_manifest',return_value=remote),patch.object(suite,'fetch',side_effect=fake_fetch),patch.object(suite,'run') as installer:
                with self.assertRaisesRegex(ValueError,'SHA-256'):suite.update(prefix)
                installer.assert_not_called()
            self.assertEqual(json.loads((prefix/'state.json').read_text(encoding='utf-8'))['version'],'1.0.0')


    @unittest.skipIf(os.name=='nt','Native installer integration runs on POSIX; Windows launcher dependency is covered by CI')
    def test_verified_update_activates_new_installer_and_component(self):
        with tempfile.TemporaryDirectory(prefix='Обновление ttools ') as temporary:
            root=Path(temporary);prefix=root/'installed'
            def make_bundle(folder,version):
                folder.mkdir()
                shutil.copytree(Path(__file__).resolve().parents[1]/'ttools',folder/'ttools',ignore=shutil.ignore_patterns('__pycache__'))
                (folder/'installer.py').write_text('from ttools.suite import main\nraise SystemExit(main())\n')
                source=folder/'components/tthings/source/tthings';source.mkdir(parents=True)
                (source/'__init__.py').write_text('')
                (source/'__main__.py').write_text('print('+repr(version)+')')
                (folder/'components/versions.json').write_text(json.dumps({'tthings':version}))
                files={p.relative_to(folder).as_posix():d.digest(p) for p in folder.rglob('*') if p.is_file()}
                manifest={'schema_version':1,'app_id':'ttools','version':version,'platform':d.platform_id(),'files':files}
                (folder/'bundle.json').write_text(json.dumps(manifest))
                return folder
            first=make_bundle(root/'first','1.0.0');second=make_bundle(root/'second','2.0.0')
            suite.install(first,prefix,selected=['tthings'],shortcuts=False)
            archive=root/'new.zip'
            with zipfile.ZipFile(archive,'w') as package:
                for path in second.rglob('*'):
                    if path.is_file():package.write(path,'ttools/'+path.relative_to(second).as_posix())
            remote={'schema_version':1,'app_id':'ttools','version':'2.0.0','artifacts':[{'platform':d.platform_id(),'url':'https://example.com/new.zip','sha256':d.digest(archive)}]}
            def fetch_local(url,target,*args):shutil.copy2(archive,target)
            with patch.object(suite,'release_manifest',return_value=remote),patch.object(suite,'fetch',side_effect=fetch_local):
                self.assertTrue(suite.update(prefix,force=True))
            state=json.loads((prefix/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(state['version'],'2.0.0')
            catalog=json.loads((Path(state['release'])/'apps.local.json').read_text(encoding='utf-8'))
            self.assertEqual(subprocess.check_output(catalog['apps'][0]['command'],text=True).strip(),'2.0.0')
            self.assertEqual(state['previous']['version'],'1.0.0')


class ProcessCleanupTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','POSIX termination/cleanup protocol')
    def test_parent_waits_for_owned_child_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ready=root/'ready';clean=root/'clean'
            child_code=("import signal,time;from pathlib import Path\n"
                        "def stop(signum,frame):\n time.sleep(.15)\n Path("+repr(str(clean))+").write_text('clean')\n raise SystemExit(0)\n"
                        "signal.signal(signal.SIGTERM,stop)\nPath("+repr(str(ready))+").write_text('ready')\nwhile True:time.sleep(.05)\n")
            parent_code="import subprocess,sys;from ttools.suite import wait_process;wait_process(subprocess.Popen([sys.executable,'-c',"+repr(child_code)+"]))"
            parent=subprocess.Popen([sys.executable,'-c',parent_code],start_new_session=True)
            try:
                deadline=time.monotonic()+3
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists())
                parent.send_signal(signal.SIGTERM)
                self.assertEqual(parent.wait(timeout=3),143)
                self.assertEqual(clean.read_text(encoding='utf-8'),'clean')
            finally:
                if parent.poll() is None:
                    parent.terminate();parent.wait(timeout=3)

if __name__=='__main__':unittest.main()
