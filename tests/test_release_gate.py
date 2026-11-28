import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.release_gate import (
    EXPECTED_ASSETS, PLATFORM_ARCHIVES, ReleaseGateError, ReleaseSnapshot,
    dereference_tag, plan_rerun, snapshot_from_api, validate_candidate_assets,
)


VERSION='1.2.3-preview.4'
COMMIT='a'*40
OTHER_COMMIT='b'*40
VERSIONS={
    'tspotify':'0.2.0','tsoundcloud':'0.1.0','ttelegram':'2026.11.18.4',
    'tvpn':'1.3.1','tthings':'0.7.2',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bundle(directory, platform):
    root=Path(directory)/'ttools'
    (root/'ttools').mkdir(parents=True)
    (root/'ttools/__init__.py').write_text(f"__version__ = '{VERSION}'\n",encoding='utf-8')
    components=root/'components'
    components.mkdir(parents=True)
    (components/'versions.json').write_text(json.dumps(VERSIONS),encoding='utf-8')
    metadata={
        'tspotify':('app.json',VERSIONS['tspotify']),
        'tsoundcloud':('app.json',VERSIONS['tsoundcloud']),
        'ttelegram':('app.json',VERSIONS['ttelegram']),
        'tthings':('app.json',VERSIONS['tthings']),
        'tvpn':('source/update.json',VERSIONS['tvpn']),
    }
    for app,(relative,version) in metadata.items():
        path=components/app/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'version':version}),encoding='utf-8')
    windows=components/'ttelegram/windows-native/app.json'
    windows.parent.mkdir(parents=True)
    windows.write_text(json.dumps({'version':'2026.11.18.7-win1'}),encoding='utf-8')
    files={p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file()}
    (root/'bundle.json').write_text(json.dumps({
        'schema_version':2,'app_id':'ttools','version':VERSION,'source_commit':COMMIT,
        'platform':platform,'complete_suite_supported':platform=='linux-x86_64',
        'unsupported_components':[],'files':files,
    }),encoding='utf-8')
    return root


def fixture_assets(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    hashes={}
    records=[]
    for name,platform in PLATFORM_ARCHIVES.items():
        with tempfile.TemporaryDirectory(prefix='ttools-bundle-',dir=directory.parent) as work:
            bundle=_bundle(Path(work),platform)
            with zipfile.ZipFile(directory/name,'w',zipfile.ZIP_DEFLATED) as package:
                for path in sorted(bundle.rglob('*')):
                    if path.is_file():package.write(path,'ttools/'+path.relative_to(bundle).as_posix())
        hashes[name]=digest(directory/name)
        records.append({'platform':platform,
            'url':f'https://github.com/user9x21imi/ttools/releases/download/v{VERSION}/{name}',
            'sha256':hashes[name],'complete_suite_supported':platform=='linux-x86_64'})
    for name in ('bootstrap.py','install.sh','install.ps1'):
        (directory/name).write_text('fixture '+name,encoding='utf-8')
        hashes[name]=digest(directory/name)
    feed={'schema_version':2,'app_id':'ttools','version':VERSION,
          'source_commit':COMMIT,'artifacts':records}
    (directory/'suite-update.json').write_text(json.dumps(feed),encoding='utf-8')
    hashes['suite-update.json']=digest(directory/'suite-update.json')
    content=''.join(f'{hashes[name]}  {name}\n' for name in sorted(hashes))
    (directory/'SHA256SUMS.txt').write_text(content,encoding='utf-8')
    hashes['SHA256SUMS.txt']=digest(directory/'SHA256SUMS.txt')
    return hashes


class ReleaseGateTests(unittest.TestCase):
    def test_local_candidate_requires_exact_assets_and_matching_bundle_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            expected=fixture_assets(root)
            actual=validate_candidate_assets(root,VERSION,COMMIT,COMMIT,COMMIT)
            self.assertEqual(actual,expected)
            self.assertEqual(set(actual),EXPECTED_ASSETS)

    def test_commit_binding_and_tag_dereference_reject_wrong_commit(self):
        with self.assertRaisesRegex(ReleaseGateError,'commit.*differ'):
            from tools.release_gate import validate_commit_binding
            validate_commit_binding(COMMIT,OTHER_COMMIT,COMMIT)
        annotated='c'*40
        resolved=dereference_tag({'sha':annotated,'type':'tag'},
            lambda sha:{'object':{'sha':COMMIT,'type':'commit'}})
        self.assertEqual(resolved,COMMIT)
        with self.assertRaisesRegex(ReleaseGateError,'unsupported Git object'):
            dereference_tag({'sha':annotated,'type':'tree'},lambda _sha:None)

    def test_asset_name_and_checksum_omissions_block_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            fixture_assets(root)
            (root/'install.ps1').unlink()
            with self.assertRaisesRegex(ReleaseGateError,'missing='):
                validate_candidate_assets(root,VERSION,COMMIT,COMMIT,COMMIT)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            fixture_assets(root)
            (root/'install.sh').write_text('tampered',encoding='utf-8')
            with self.assertRaisesRegex(ReleaseGateError,'Checksum file mismatch'):
                validate_candidate_assets(root,VERSION,COMMIT,COMMIT,COMMIT)

    def test_update_feed_and_embedded_archives_must_share_tested_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            fixture_assets(root)
            feed_path=root/'suite-update.json'
            feed=json.loads(feed_path.read_text())
            feed['source_commit']=OTHER_COMMIT
            feed_path.write_text(json.dumps(feed),encoding='utf-8')
            expected={name:digest(path) for name in EXPECTED_ASSETS if name!='SHA256SUMS.txt'
                      for path in (root/name,)}
            (root/'SHA256SUMS.txt').write_text(
                ''.join(f'{expected[name]}  {name}\n' for name in sorted(expected)),encoding='utf-8')
            with self.assertRaisesRegex(ReleaseGateError,'Update feed version/source commit mismatch'):
                validate_candidate_assets(root,VERSION,COMMIT,COMMIT,COMMIT)

    def test_draft_recovery_only_resumes_matching_subset(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected=fixture_assets(Path(temporary))
            subset={name:expected[name] for name in list(expected)[:3]}
            draft=ReleaseSnapshot('v'+VERSION,COMMIT,True,False,subset)
            plan=plan_rerun('v'+VERSION,COMMIT,expected,draft,COMMIT,tag_lookup_complete=True)
            self.assertEqual(plan.action,'resume_draft')
            self.assertEqual(set(plan.missing_assets),set(expected)-set(subset))
            conflict=ReleaseSnapshot('v'+VERSION,COMMIT,True,False,{**subset,next(iter(subset)):'0'*64})
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,conflict,COMMIT,tag_lookup_complete=True).action,'block')
            extra=ReleaseSnapshot('v'+VERSION,COMMIT,True,False,{**subset,'unexpected.zip':'1'*64})
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,extra,COMMIT,tag_lookup_complete=True).action,'block')

    def test_version_rerun_is_noop_only_for_exact_immutable_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected=fixture_assets(Path(temporary))
            unverified=plan_rerun('v'+VERSION,COMMIT,expected)
            self.assertEqual(unverified.action,'block')
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,tag_lookup_complete=True).action,'create_draft')
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,tag_commit=OTHER_COMMIT,tag_lookup_complete=True).action,'block')
            draft=ReleaseSnapshot('v'+VERSION,COMMIT,True,False,expected)
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,draft,tag_lookup_complete=True).action,'publish_draft')
            mutable=ReleaseSnapshot('v'+VERSION,COMMIT,False,False,expected)
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,mutable,tag_lookup_complete=True).action,'block')
            immutable=ReleaseSnapshot('v'+VERSION,COMMIT,False,True,expected)
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,immutable,tag_lookup_complete=True).action,'no_op')
            incomplete=ReleaseSnapshot('v'+VERSION,COMMIT,False,True,{})
            self.assertEqual(plan_rerun('v'+VERSION,COMMIT,expected,incomplete,tag_lookup_complete=True).action,'block')

    def test_github_asset_snapshot_requires_sha256_digests(self):
        release={'tag_name':'v'+VERSION,'draft':True,'immutable':False,
                 'assets':[{'name':'install.sh','digest':'sha256:'+'d'*64}]}
        snapshot=snapshot_from_api(release,COMMIT)
        self.assertEqual(snapshot.assets['install.sh'],'d'*64)
        with self.assertRaisesRegex(ReleaseGateError,'missing digest'):
            snapshot_from_api({**release,'assets':[{'name':'install.sh','digest':None}]},COMMIT)


if __name__=='__main__':
    unittest.main()
