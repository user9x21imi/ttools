import json
import unittest
from unittest.mock import patch
import urllib.error
import bootstrap


class ReleaseDiscoveryTests(unittest.TestCase):
    def feed(self, *tags):
        return ('<feed xmlns="http://www.w3.org/2005/Atom">'+''.join(
            f'<entry><link href="https://github.com/{bootstrap.REPO}/releases/tag/{tag}"/></entry>'
            for tag in tags)+'</feed>').encode()

    def test_preview_uses_public_feed_and_direct_asset(self):
        manifest={'schema_version':1,'app_id':'ttools','version':'1.1.0-preview.1'}
        with patch.object(bootstrap,'read',side_effect=[self.feed('v1.1.0-preview.1'),json.dumps(manifest).encode()]) as read:
            self.assertEqual(bootstrap.release_manifest(True),manifest)
        self.assertTrue(read.call_args_list[0].args[0].endswith('/releases.atom'))
        self.assertIn('/releases/download/v1.1.0-preview.1/suite-update.json',read.call_args_list[1].args[0])
        self.assertTrue(all('api.github.com' not in c.args[0] for c in read.call_args_list))

    def test_schema_two_release_requires_and_preserves_source_commit(self):
        commit='c'*40
        manifest={'schema_version':2,'app_id':'ttools','version':'1.2.0-preview.1','source_commit':commit}
        with patch.object(bootstrap,'read',side_effect=[self.feed('v1.2.0-preview.1'),json.dumps(manifest).encode()]):
            self.assertEqual(bootstrap.release_manifest(True),manifest)
        invalid=dict(manifest,source_commit='short')
        with patch.object(bootstrap,'read',side_effect=[self.feed('v1.2.0-preview.1'),json.dumps(invalid).encode()]):
            with self.assertRaisesRegex(ValueError,'source commit'):
                bootstrap.release_manifest(True)

    def test_stable_excludes_preview_and_foreign_links(self):
        with patch.object(bootstrap,'read',return_value=self.feed('v1.1.0-preview.1','other-package')) as read:
            with self.assertRaisesRegex(RuntimeError,'No published'):bootstrap.release_manifest()
        self.assertEqual(read.call_count,1)

    def test_missing_manifest_skips_unrelated_release(self):
        manifest={'schema_version':1,'app_id':'ttools','version':'1.0.0'}
        missing=urllib.error.HTTPError('https://github.com',404,'missing',{},None)
        with patch.object(bootstrap,'read',side_effect=[self.feed('v2.0.0','v1.0.0'),missing,json.dumps(manifest).encode()]):
            self.assertEqual(bootstrap.release_manifest(),manifest)

    def test_tag_version_mismatch_rejected(self):
        with patch.object(bootstrap,'read',return_value=b'{"schema_version":1,"app_id":"ttools","version":"9.0.0"}'):
            with self.assertRaisesRegex(ValueError,'mismatch'):bootstrap.release_manifest(tag='v1.0.0')

    def test_permission_error_not_silenced(self):
        denied=urllib.error.HTTPError('https://github.com',403,'denied',{},None)
        with patch.object(bootstrap,'read',side_effect=denied):
            with self.assertRaises(urllib.error.HTTPError):bootstrap.release_manifest(tag='v1.0.0')
