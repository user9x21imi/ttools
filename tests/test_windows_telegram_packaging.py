import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ttools.distribution import digest
from tools import download_windows_telegram


class WindowsTelegramPackagingTests(unittest.TestCase):
    def fixture(self, root):
        override_root = root / 'components/ttelegram/windows-native'
        runtime = root / 'runtime/windows-native'
        runtime.mkdir(parents=True)
        inventory = {}
        for name in download_windows_telegram.REVIEWED_OVERRIDES:
            source = override_root / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(('reviewed:' + name).encode())
            target = runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(('author:' + name).encode())
            inventory[name] = digest(target)
        untouched = runtime / 'source/platform_tools.py'
        untouched.parent.mkdir(parents=True, exist_ok=True)
        untouched.write_text('author-only platform adapter', encoding='utf-8')
        inventory['source/platform_tools.py'] = digest(untouched)
        (runtime / 'files.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
        (runtime / 'SHA256SUMS.txt').write_text(
            ''.join(f'{value}  {name}\n' for name, value in inventory.items()), encoding='utf-8')
        return override_root, runtime, inventory

    def test_copies_reviewed_ui_sources_and_refreshes_both_inventories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            override_root, runtime, inventory = self.fixture(root)
            with patch.object(download_windows_telegram, 'ROOT', root):
                download_windows_telegram.apply_integration_fixes(runtime, inventory)

            installed = json.loads((runtime / 'files.json').read_text(encoding='utf-8'))
            checksum_rows = {}
            for line in (runtime / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
                sha, name = line.split('  ', 1)
                self.assertNotIn(name, checksum_rows)
                checksum_rows[name] = sha
            self.assertEqual(set(installed), set(checksum_rows))
            self.assertEqual(installed, checksum_rows)
            for name in download_windows_telegram.REVIEWED_OVERRIDES:
                self.assertEqual((runtime / name).read_bytes(), (override_root / name).read_bytes())
                self.assertEqual(installed[name], digest(runtime / name))
            self.assertEqual((runtime / 'source/platform_tools.py').read_text(encoding='utf-8'),
                             'author-only platform adapter')

    def test_rejects_author_files_json_and_checksum_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, runtime, inventory = self.fixture(root)
            (runtime / 'SHA256SUMS.txt').write_text('0' * 64 + '  source/platform_tools.py\n', encoding='utf-8')
            with patch.object(download_windows_telegram, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'inventories differ'):
                    download_windows_telegram.apply_integration_fixes(runtime, inventory)

    def test_adds_reviewed_artifacts_missing_from_the_author_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, runtime, inventory = self.fixture(root)
            name = 'tests/artifacts/chat-list.png'
            inventory.pop(name)
            (runtime / 'files.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
            (runtime / 'SHA256SUMS.txt').write_text(
                ''.join(f'{value}  {item}\n' for item, value in inventory.items()), encoding='utf-8')
            with patch.object(download_windows_telegram, 'ROOT', root):
                download_windows_telegram.apply_integration_fixes(runtime, inventory)

            installed = json.loads((runtime / 'files.json').read_text(encoding='utf-8'))
            checksums = dict(line.split('  ', 1)[::-1] for line in
                             (runtime / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines())
            self.assertIn(name, installed)
            self.assertEqual(installed[name], digest(runtime / name))
            self.assertEqual(checksums[name], installed[name])

    def test_requires_each_reviewed_source_before_installing_any_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            override_root, runtime, inventory = self.fixture(root)
            missing = override_root / download_windows_telegram.REVIEWED_OVERRIDES[-1]
            missing.unlink()
            before = {name: (runtime / name).read_bytes() for name in download_windows_telegram.REVIEWED_OVERRIDES}
            with patch.object(download_windows_telegram, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'Missing reviewed Windows Telegram override'):
                    download_windows_telegram.apply_integration_fixes(runtime, inventory)
            self.assertEqual(before, {name: (runtime / name).read_bytes() for name in download_windows_telegram.REVIEWED_OVERRIDES})


if __name__ == '__main__':
    unittest.main()
