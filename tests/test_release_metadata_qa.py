import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.build_release import resolve_source_commit, suite_version_for_package
from ttools import distribution
from ttools.distribution import validate_component_versions, valid_source_commit, verify_bundle
from ttools import suite


class ReleaseMetadataQATests(unittest.TestCase):
    def test_pep440_and_public_suite_versions_have_one_mapping(self):
        self.assertEqual(suite_version_for_package('1.1.0.dev4'), '1.1.0-preview.4')
        self.assertEqual(suite_version_for_package('1.1.0'), '1.1.0')
        with self.assertRaisesRegex(RuntimeError, 'Unsupported Python package version'):
            suite_version_for_package('1.1.0a1')

    def test_source_commit_requires_full_lowercase_git_sha(self):
        self.assertTrue(valid_source_commit('a' * 40))
        for invalid in ('a' * 39, 'A' * 40, 'g' * 40, None):
            self.assertFalse(valid_source_commit(invalid))

    def test_builder_binds_github_sha_to_clean_checkout(self):
        sha = 'a' * 40
        with patch('tools.build_release.subprocess.check_output', side_effect=[sha + '\n', '']), \
                patch.dict(os.environ, {'GITHUB_SHA': sha}):
            self.assertEqual(resolve_source_commit(Path('/checkout')), sha)
        with patch('tools.build_release.subprocess.check_output', side_effect=[sha + '\n', ' M file']), \
                patch.dict(os.environ, {'GITHUB_SHA': sha}):
            with self.assertRaisesRegex(RuntimeError, 'clean checkout'):
                resolve_source_commit(Path('/checkout'))

    def test_schema_two_bundle_requires_commit_provenance(self):
        with tempfile.TemporaryDirectory(prefix='ttools-provenance-') as temporary:
            root = Path(temporary)
            (root / 'bundle.json').write_text(json.dumps({
                'schema_version': 2, 'app_id': 'ttools', 'version': '1.0.0',
                'source_commit': 'bad-sha', 'files': {},
            }), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'source commit'):
                verify_bundle(root)

    def test_runtime_feed_accepts_valid_v2_identity_and_rejects_missing_identity(self):
        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://github.com/user9x21imi/ttools/releases/tag/v1.0.0"/></entry></feed>'
        commit = 'b' * 40
        manifest = {'schema_version': 2, 'app_id': 'ttools', 'version': '1.0.0',
                    'source_commit': commit}

        def write_feed(_url, path, *_args):
            Path(path).write_bytes(feed)

        with patch.object(distribution, 'fetch', side_effect=write_feed), \
                patch.object(distribution, 'read_remote_json', return_value=manifest):
            self.assertEqual(distribution.latest_suite_manifest(), manifest)
        with patch.object(distribution, 'fetch', side_effect=write_feed), \
                patch.object(distribution, 'read_remote_json', return_value={**manifest, 'source_commit': None}):
            with self.assertRaisesRegex(ValueError, 'source commit'):
                distribution.latest_suite_manifest()

    def test_component_catalog_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            components = root / 'components'
            components.mkdir()
            versions = {
                'tspotify': '0.2.0', 'tsoundcloud': '0.1.0',
                'ttelegram': '2026.11.18.4', 'tvpn': '1.3.1', 'tthings': '0.7.2',
            }
            (components / 'versions.json').write_text(json.dumps(versions), encoding='utf-8')
            metadata = {
                'tspotify': ('app.json', '0.2.1'),
                'tsoundcloud': ('app.json', '0.1.0'),
                'ttelegram': ('app.json', '2026.11.18.4'),
                'tthings': ('app.json', '0.7.2'),
                'tvpn': ('source/update.json', '1.3.1'),
            }
            for app, (relative, version) in metadata.items():
                path = components / app / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({'version': version}), encoding='utf-8')
            windows = components / 'ttelegram/windows-native/app.json'
            windows.parent.mkdir(parents=True)
            windows.write_text(json.dumps({'version': '2026.11.18.7-win1'}), encoding='utf-8')
            path = components / 'tspotify/app.json'
            path.write_text(json.dumps({'version': '0.2.0'}), encoding='utf-8')
            self.assertEqual(validate_component_versions(root, strict=True), versions)
            path.write_text(json.dumps({'version': '0.2.1'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'tspotify catalog=0.2.0 metadata=0.2.1'):
                validate_component_versions(root, strict=True)

    @unittest.skipIf(sys.platform == 'win32', 'runner fixture uses POSIX temporary state')
    def test_direct_child_launch_checks_suite_updates(self):
        with tempfile.TemporaryDirectory(prefix='ttools-direct-child-') as temporary:
            prefix = Path(temporary)
            release = prefix / 'release'
            release.mkdir()
            (release / 'apps.local.json').write_text(json.dumps({'apps': [{
                'id': 'tthings', 'command': [sys.executable], 'env': {},
            }]}), encoding='utf-8')
            (prefix / 'state.json').write_text(json.dumps({
                'release': str(release), 'python': sys.executable,
            }), encoding='utf-8')
            child = Mock()
            with patch.dict(os.environ, {'TTOOLS_AUTOUPDATE': '1'}), \
                    patch.object(suite.sys, 'platform', 'linux'), \
                    patch.object(suite, 'update', return_value=False) as update, \
                    patch.object(suite.subprocess, 'Popen', return_value=child), \
                    patch.object(suite, 'wait_process', return_value=0):
                self.assertEqual(suite.launch_installed(prefix, ['--app', 'tthings']), 0)
            update.assert_called_once_with(prefix.resolve(), automatic=True)

    def test_default_suite_rollback_keeps_tvpn_guard_and_active_state(self):
        with tempfile.TemporaryDirectory(prefix='ttools-tvpn-rollback-') as temporary:
            prefix = Path(temporary)
            active = prefix / 'releases/active'
            previous = prefix / 'releases/previous'
            active.mkdir(parents=True)
            previous.mkdir()
            prior = {'version': '1.0.0', 'release': str(previous),
                     'options': {'components': ['tspotify', 'tsoundcloud', 'ttelegram', 'tthings', 'tvpn']}}
            state = {'version': '1.0.1', 'release': str(active),
                     'options': {'components': ['tspotify', 'tsoundcloud', 'ttelegram', 'tthings', 'tvpn']},
                     'previous': prior}
            state_path = prefix / 'state.json'
            state_path.write_text(json.dumps(state), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'TVPN protected backend'):
                suite.rollback(prefix)
            self.assertEqual(json.loads(state_path.read_text(encoding='utf-8')), state)


if __name__ == '__main__':
    unittest.main()
