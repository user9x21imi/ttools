"""Isolated full-suite updater E2E. No account, host packages, or VPN is used."""
import errno
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ttools import distribution as dist
from ttools import suite

ROOT=Path(__file__).resolve().parents[1]
QA_RUNTIME=(
    "import json,os,sys\nfrom pathlib import Path\n"
    "def record(kind,app,version):\n"
    " p=os.environ.get('TTOOLS_QA_TRACE')\n"
    " if p:\n"
    "  with Path(p).open('a',encoding='utf-8') as f: f.write(json.dumps({'event':kind,'app':app,'version':version},sort_keys=True)+'\\n')\n"
    "def main(app,version):\n"
    " record('launch',app,version)\n"
    " print('launched:'+app+':'+version)\n"
    " sys.exit(37 if os.environ.get('TTOOLS_QA_FAIL_START')==app else 0)\n")
QA_LAUNCH=(
    "import sys\nfrom qa_runtime import main,record\n"
    "app,version=sys.argv[1],sys.argv[2]\n"
    "if any(x in ('stop','--stop-managed','--stop-only') for x in sys.argv[3:]): record('stop',app,version)\n"
    "else: main(app,version)\n")


def _record(kind, app=None, version=None, **extra):
    path=os.environ.get('TTOOLS_QA_TRACE')
    if not path:return
    event={'event':kind,'app':app,'version':version,**extra}
    with Path(path).open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(event,sort_keys=True)+'\n')


def _make_bundle(root,version,commit):
    root.mkdir(parents=True)
    shutil.copytree(ROOT/'ttools',root/'ttools',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    module=root/'ttools/__init__.py'
    source=module.read_text(encoding='utf-8')
    source,count=re.subn(r"__version__\s*=\s*['\"][^'\"]+['\"]",
                         f"__version__ = '{version}'",source,count=1)
    if count!=1:raise AssertionError('suite version marker not found')
    module.write_text(source,encoding='utf-8')
    shutil.copy2(ROOT/'installer.py',root/'installer.py')
    (root/'qa_runtime.py').write_text(QA_RUNTIME,encoding='utf-8')
    (root/'qa-launch.py').write_text(QA_LAUNCH,encoding='utf-8')
    components=root/'components'
    # The bundle uses real launcher code and official version metadata. Only
    # app source/runtime payloads are omitted because the E2E executor replaces
    # their installers with safe local commands.
    components.mkdir()
    shutil.copy2(ROOT/'components/versions.json',components/'versions.json')
    for app in suite.APP_IDS:
        folder=components/app
        folder.mkdir(parents=True,exist_ok=True)
        source_meta=ROOT/'components'/app/'app.json'
        if source_meta.is_file():shutil.copy2(source_meta,folder/'app.json')
        if app=='tvpn':
            metadata=folder/'source';metadata.mkdir()
            shutil.copy2(ROOT/'components/tvpn/source/update.json',metadata/'update.json')
    windows=components/'ttelegram/windows-native';windows.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'components/ttelegram/windows-native/app.json',windows/'app.json')
    files={p.relative_to(root).as_posix():dist.digest(p)
           for p in root.rglob('*') if p.is_file()}
    manifest={'schema_version':2,'app_id':'ttools','version':version,
              'platform':dist.platform_id(),'source_commit':commit,'files':files}
    (root/'bundle.json').write_text(json.dumps(manifest,sort_keys=True),encoding='utf-8')
    dist.verify_bundle(root)
    return manifest


def _archive(bundle,path):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as output:
        for item in sorted(bundle.rglob('*')):
            if item.is_file():output.write(item,'ttools/'+item.relative_to(bundle).as_posix())


def _qa_install_component(app,release,defer_system=False):
    if os.environ.get('TTOOLS_QA_FAIL_COMPONENT')==app:
        raise RuntimeError('synthetic '+app+' installation failure')
    versions=json.loads((release/'components/versions.json').read_text(encoding='utf-8'))
    version=versions[app]
    (release/'qa_runtime.py').write_text(QA_RUNTIME,encoding='utf-8')
    (release/'qa-launch.py').write_text(QA_LAUNCH,encoding='utf-8')
    dest=release/'apps'/app
    dest.mkdir(parents=True,exist_ok=True)
    _record('install',app,version,defer_system=defer_system)
    (dest/'run.lock').touch()
    if app in ('ttelegram','tvpn'):
        (dest/'manage.py').write_text(
            'import sys\nfrom pathlib import Path\n'
            f"sys.path.insert(0,{str(release)!r})\n"
            'from qa_runtime import record\n'
            f"record('stop',{app!r},{version!r})\n",encoding='utf-8')
    return [sys.executable,str(release/'qa-launch.py'),app,version],{}


def _run_local_installer(argv,**kwargs):
    """Keep host-specific installers isolated while exercising suite.install."""
    command=[str(value) for value in argv]
    if len(command)>1 and Path(command[1]).name=='installer.py':
        prefix=Path(command[command.index('--prefix')+1])
        selected=command[command.index('--components')+1].split(',')
        suite.install(Path(command[1]).parent,prefix,selected=selected,
                      allow_partial='--allow-partial' in command,
                      defer_system='--defer-system' in command,
                      shortcuts='--no-shortcuts' not in command)
        return None
    return subprocess.run(command,check=True,**kwargs)


class CompleteSuiteUpdateE2E(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='ttools-full-suite-e2e-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.prefix=self.root/'isolated-prefix'
        self.trace=self.root/'events.jsonl'
        self.hooks=self.root/'python-hooks';self.hooks.mkdir()
        (self.hooks/'sitecustomize.py').write_text(
            "import json,os,sys\nfrom pathlib import Path\n"
            "if os.environ.get('TTOOLS_QA_SANDBOX')=='1':\n"
            " release=Path(os.environ['TTOOLS_QA_RELEASE'])\n"
            " sys.path.insert(0,str(release))\n"
            " from ttools import suite\n"
            " def safe_setup(selected_release,target):\n"
            "  selected_release=Path(selected_release)\n"
            "  manifest=json.loads((selected_release/'bundle.json').read_text())\n"
            "  state=json.loads((selected_release.parents[1]/'state.json').read_text())\n"
            "  event={'event':'system_setup','app':'tvpn','version':manifest['version'],'target':target,'release':str(selected_release),'active_version':state['version']}\n"
            "  with Path(os.environ['TTOOLS_QA_TRACE']).open('a',encoding='utf-8') as stream: stream.write(json.dumps(event,sort_keys=True)+'\\n')\n"
            " suite.configure_tvpn_system=safe_setup\n",encoding='utf-8')
        self.old=self.root/'public-1.1.0-preview.1'
        self.new=self.root/'candidate-1.1.0-preview.4'
        self.old_manifest=_make_bundle(self.old,'1.1.0-preview.1','1'*40)
        self.new_manifest=_make_bundle(self.new,'1.1.0-preview.4','4'*40)
        self.old_archive=self.root/'old.zip'
        self.new_archive=self.root/'candidate.zip'
        _archive(self.old,self.old_archive)
        _archive(self.new,self.new_archive)
        self.feed={'schema_version':1,'app_id':'ttools','version':'1.1.0-preview.4',
                   'source_commit':'4'*40,'artifacts':[{
                       'platform':dist.platform_id(),'url':'https://qa.invalid/candidate.zip',
                       'sha256':dist.digest(self.new_archive)}]}
        self.env=patch.dict(os.environ,{'TTOOLS_QA_TRACE':str(self.trace),'TTOOLS_AUTOUPDATE':'0'},clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.component_patch=patch.object(suite,'install_component',side_effect=_qa_install_component)
        self.component_patch.start()
        self.addCleanup(self.component_patch.stop)
        self.prereq_patch=patch.object(suite,'linux_prerequisites')
        self.prereq_patch.start()
        self.addCleanup(self.prereq_patch.stop)
        self.run_patch=patch.object(suite,'run',side_effect=_run_local_installer)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.system_patch=patch.object(suite,'configure_tvpn_system',side_effect=self._fake_system_setup)
        self.system_patch.start()
        self.addCleanup(self.system_patch.stop)

    def _fake_system_setup(self,release,target):
        release=Path(release)
        state=json.loads((release.parents[1]/'state.json').read_text(encoding='utf-8'))
        manifest=json.loads((release/'bundle.json').read_text(encoding='utf-8'))
        _record('system_setup','tvpn',manifest['version'],target=target,
                release=str(release),active_version=state['version'])

    def _runner_env(self,state,**overrides):
        release=Path(state['release'])
        values={'TTOOLS_AUTOUPDATE':'0','TTOOLS_QA_SANDBOX':'1',
                'TTOOLS_QA_RELEASE':str(release),'TTOOLS_QA_TRACE':str(self.trace),
                'PYTHONPATH':os.pathsep.join((str(self.hooks),str(release)))}
        values.update(overrides)
        return dict(os.environ,**values)

    def _events(self):
        if not self.trace.exists():return []
        return [json.loads(line) for line in self.trace.read_text(encoding='utf-8').splitlines()]

    def _clear_events(self):self.trace.unlink(missing_ok=True)

    def _install_initial(self):
        return suite.install(self.old,self.prefix,selected=suite.APP_IDS,shortcuts=False)

    def _feed_update(self,fetch=None):
        def default_fetch(url,target,*args,**kwargs):shutil.copyfile(self.new_archive,target)
        with patch.object(suite,'release_manifest',return_value=self.feed), \
                patch.object(suite,'fetch',side_effect=fetch or default_fetch):
            return suite.update(self.prefix,force=True)

    def _assert_manifest_installed(self,state,expected):
        release=Path(state['release'])
        actual=json.loads((release/'bundle.json').read_text(encoding='utf-8'))
        self.assertEqual(actual['source_commit'],expected['source_commit'])
        self.assertEqual(actual['files'],expected['files'])
        self.assertEqual(state['source_commit'],expected['source_commit'])
        for name,sha in expected['files'].items():
            self.assertEqual(dist.digest(release/name),sha,name)

    def _launch_all(self,state):
        catalog=json.loads((Path(state['release'])/'apps.local.json').read_text(encoding='utf-8'))
        self.assertEqual([app['id'] for app in catalog['apps']],list(suite.APP_IDS))
        for app in catalog['apps']:
            result=subprocess.run([sys.executable,str(self.prefix/'runner.py'),'--app',app['id']],
                                  check=False,text=True,capture_output=True,
                                  env=self._runner_env(state))
            self.assertEqual(result.returncode,0,app['id']+': '+result.stderr)
            self.assertIn('launched:'+app['id']+':',result.stdout)

    def test_clean_full_install_and_launch_every_official_linux_app(self):
        state=self._install_initial()
        self.assertTrue(state['complete'])
        self.assertEqual(state['options']['components'],list(suite.APP_IDS))
        self.assertEqual([e['app'] for e in self._events() if e['event']=='install'],list(suite.APP_IDS))
        self.assertEqual(len([e for e in self._events() if e['event']=='system_setup']),1)
        self._launch_all(state)
        launched=[e['app'] for e in self._events() if e['event']=='launch']
        self.assertEqual(launched,list(suite.APP_IDS))
        self._assert_manifest_installed(state,self.old_manifest)

    def test_full_upgrade_failure_matrix_data_manifest_startup_and_tvpn_rollback(self):
        old_state=self._install_initial()
        user_data={
            'settings.json':'{"theme":"custom","keep":true}\n',
            'tokens.json':'{"access_token":"synthetic-token"}\n',
            'sessions/history.json':'[{"session":"synthetic"}]\n',
        }
        for relative,content in user_data.items():
            path=self.prefix/'user-data'/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8')

        # A network interruption never reaches installation or changes active state.
        with self.assertRaisesRegex(OSError,'synthetic network interruption'):
            self._feed_update(fetch=lambda *_args,**_kwargs: (_ for _ in ()).throw(OSError('synthetic network interruption')))
        self.assertEqual(json.loads((self.prefix/'state.json').read_text())['version'],old_state['version'])
        self.assertFalse((self.prefix/'pending').exists())

        # Even a correctly advertised checksum cannot make an invalid ZIP install.
        corrupt=self.root/'corrupt.zip';corrupt.write_bytes(b'not a zip archive')
        corrupt_feed=dict(self.feed,artifacts=[dict(self.feed['artifacts'][0],sha256=dist.digest(corrupt))])
        with patch.object(suite,'release_manifest',return_value=corrupt_feed), \
                patch.object(suite,'fetch',side_effect=lambda _url,target,*_args,**_kwargs:shutil.copyfile(corrupt,target)):
            with self.assertRaises(zipfile.BadZipFile):suite.update(self.prefix,force=True)
        self.assertEqual(json.loads((self.prefix/'state.json').read_text())['version'],old_state['version'])

        # Simulate ENOSPC during the release copy, after a partial directory exists.
        original_copytree=shutil.copytree
        def no_space(source,destination,*args,**kwargs):
            destination=Path(destination)
            if destination.parent==self.prefix/'releases':
                destination.mkdir(parents=True,exist_ok=True)
                (destination/'partial').write_text('incomplete')
                raise OSError(errno.ENOSPC,'No space left on device')
            return original_copytree(source,destination,*args,**kwargs)
        with patch.object(shutil,'copytree',side_effect=no_space):
            with self.assertRaises(OSError) as failure:self._feed_update()
        self.assertEqual(failure.exception.errno,errno.ENOSPC)
        self.assertEqual(json.loads((self.prefix/'state.json').read_text())['version'],old_state['version'])
        self.assertEqual([p.name for p in (self.prefix/'releases').iterdir()],
                         [Path(old_state['release']).name])
        self.assertFalse((self.prefix/'pending').exists())

        # Installation failure in the final (protected) component leaves the public suite active.
        self._clear_events()
        with patch.dict(os.environ,{'TTOOLS_QA_FAIL_COMPONENT':'tvpn'}):
            with self.assertRaisesRegex(RuntimeError,'synthetic tvpn installation failure'):
                self._feed_update()
        active=json.loads((self.prefix/'state.json').read_text(encoding='utf-8'))
        self.assertEqual(active['version'],old_state['version'])
        self.assertFalse((self.prefix/'pending').exists())
        self.assertFalse(any(e['event']=='system_setup' for e in self._events()))

        # A complete candidate activates only after every component is staged.
        self._clear_events()
        self.assertTrue(self._feed_update())
        active=json.loads((self.prefix/'state.json').read_text(encoding='utf-8'))
        self.assertEqual(active['version'],'1.1.0-preview.4')
        self.assertTrue(active['complete'])
        self._assert_manifest_installed(active,self.new_manifest)
        events=self._events()
        stop_ids=[e['app'] for e in events if e['event']=='stop']
        self.assertEqual(stop_ids,['tspotify','ttelegram','tthings','tvpn'])
        install_ids=[e['app'] for e in events if e['event']=='install']
        self.assertEqual(install_ids,list(suite.APP_IDS))
        setup=next(e for e in events if e['event']=='system_setup')
        stop_last=max(i for i,e in enumerate(events) if e['event']=='stop')
        install_first=min(i for i,e in enumerate(events) if e['event']=='install')
        install_last=max(i for i,e in enumerate(events) if e['event']=='install')
        setup_index=events.index(setup)
        self.assertLess(stop_last,install_first)
        self.assertLess(install_last,setup_index)
        self.assertEqual(setup['version'],'1.1.0-preview.4')
        self._launch_all(active)

        # A failed child startup is returned to the caller without corrupting state;
        # the explicit suite rollback then restores the previous working release.
        active=json.loads((self.prefix/'state.json').read_text(encoding='utf-8'))
        with patch.dict(os.environ,{'TTOOLS_QA_FAIL_START':'tsoundcloud'}):
            failed=subprocess.run([sys.executable,str(self.prefix/'runner.py'),'--app','tsoundcloud'],
                                  check=False,text=True,capture_output=True,
                                  env=self._runner_env(active,TTOOLS_QA_FAIL_START='tsoundcloud'))
            self.assertEqual(failed.returncode,37)
        self.assertEqual(json.loads((self.prefix/'state.json').read_text())['version'],'1.1.0-preview.4')

        # Repeating the same update is a no-op and does not redownload the archive.
        with patch.object(suite,'release_manifest',return_value=self.feed), \
                patch.object(suite,'fetch',side_effect=AssertionError('same release must not download')):
            self.assertFalse(suite.update(self.prefix,force=True))
            self.assertFalse(suite.update(self.prefix,force=True))

        self._clear_events()
        rollback=subprocess.run([sys.executable,str(self.prefix/'runner.py'),'--rollback'],
                                check=False,text=True,capture_output=True,
                                env=self._runner_env(active))
        self.assertEqual(rollback.returncode,0,rollback.stderr)
        rolled_back=json.loads((self.prefix/'state.json').read_text(encoding='utf-8'))
        self.assertEqual(rolled_back['version'],'1.1.0-preview.1')
        self._assert_manifest_installed(rolled_back,self.old_manifest)
        rollback_setup=next(e for e in self._events() if e['event']=='system_setup')
        self.assertEqual(rollback_setup['version'],'1.1.0-preview.1')
        self.assertEqual(len([e for e in self._events() if e['event']=='stop']),4)
        self._launch_all(rolled_back)

        for relative,content in user_data.items():
            self.assertEqual((self.prefix/'user-data'/relative).read_text(encoding='utf-8'),content)

    @unittest.skipUnless((ROOT/'dist/ttools-linux-x86_64.zip').is_file(),
                         'local copy of the published preview.1 Linux artifact is not present')
    def test_published_preview1_artifact_upgrades_to_complete_five_app_suite(self):
        archive=ROOT/'dist/ttools-linux-x86_64.zip'
        release_meta=json.loads((ROOT/'dist/suite-update.json').read_text(encoding='utf-8'))
        published=next(item for item in release_meta['artifacts']
                       if item['platform']=='linux-x86_64')
        self.assertEqual(dist.digest(archive),published['sha256'])
        unpacked=self.root/'published-unpacked'
        dist.extract_zip(archive,unpacked)
        public_bundle=unpacked/'ttools'
        public_manifest=dist.verify_bundle(public_bundle)
        self.assertEqual(public_manifest['version'],'1.1.0-preview.1')
        self.assertTrue(published['complete_suite_supported'])
        old_components=['tspotify','ttelegram','tthings','tvpn']
        old_state=suite.install(public_bundle,self.prefix,selected=old_components,shortcuts=False)
        self.assertEqual(set(old_state['options']['components']),set(old_components))

        # The local preview.4 fixture contains all five components; the updater
        # migrates the formerly complete four-app selection by adding SoundCloud.
        self.assertTrue(self._feed_update())
        active=json.loads((self.prefix/'state.json').read_text(encoding='utf-8'))
        self.assertTrue(active['complete'])
        self.assertEqual(active['options']['components'],list(suite.APP_IDS))
        self._assert_manifest_installed(active,self.new_manifest)
        self._launch_all(active)


if __name__=='__main__':unittest.main()
