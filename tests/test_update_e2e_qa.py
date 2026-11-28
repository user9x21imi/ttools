"""Offline, isolated end-to-end QA for the suite updater.

This test uses temporary synthetic release bundles and a local JSON feed. It
does not contact GitHub, alter a user's installation, or start a VPN/backend.
The source_commit marker is deliberately part of the candidate payload so the
test proves that the installed package contains the candidate's bytes, not
merely its version label. Production bundles still need builder provenance.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ttools import distribution as dist
from ttools import suite


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _make_release(directory, version, source_commit, behavior):
    directory.mkdir(parents=True)
    shutil.copytree(ROOT / "ttools", directory / "ttools",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (directory / "installer.py").write_text(
        "from ttools.suite import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    app = directory / "components/tthings/source/tthings"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "__main__.py").write_text(
        "print(" + repr(f"functional:{version}:{source_commit}:{behavior}") + ")\n",
        encoding="utf-8",
    )
    (directory / "components/versions.json").write_text(
        json.dumps({"tthings": version}), encoding="utf-8"
    )
    # This file models release provenance that production build_release.py
    # does not currently record. It is included in the verified file inventory.
    identity = {"version": version, "source_commit": source_commit}
    (directory / "source-identity.json").write_text(
        json.dumps(identity, sort_keys=True), encoding="utf-8"
    )
    files = {
        path.relative_to(directory).as_posix(): dist.digest(path)
        for path in directory.rglob("*") if path.is_file()
    }
    manifest = {
        "schema_version": 1,
        "app_id": "ttools",
        "version": version,
        "platform": dist.platform_id(),
        "source_commit": source_commit,
        "files": files,
    }
    (directory / "bundle.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _archive(bundle, destination):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                output.write(path, "ttools/" + path.relative_to(bundle).as_posix())


def _run_first_app(state):
    catalog = json.loads((Path(state["release"]) / "apps.local.json").read_text())
    return subprocess.check_output(catalog["apps"][0]["command"], text=True).strip()


def _run_with_local_installer(argv, env=None):
    """Run the app command normally, but keep the updater's installer in-process.

    This avoids installing wheels or modifying PATH on the host. The real
    synthetic app still launches as a child process after activation.
    """
    command = [str(item) for item in argv]
    if len(command) > 1 and Path(command[1]).name == "installer.py":
        prefix = Path(command[command.index("--prefix") + 1])
        components = command[command.index("--components") + 1].split(",")
        suite.install(
            Path(command[1]).parent,
            prefix,
            selected=components,
            allow_partial="--allow-partial" in command,
            defer_system="--defer-system" in command,
            shortcuts="--no-shortcuts" not in command,
        )
        return None
    return subprocess.run(command, check=True, env=env)


class UpdateEndToEndQATests(unittest.TestCase):
    def test_local_feed_download_install_launch_data_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix="ttools-e2e-qa-") as temporary:
            root = Path(temporary)
            prefix = root / "isolated-install"
            old_commit = "1" * 40
            candidate_commit = "2" * 40
            old = root / "old-bundle"
            candidate = root / "candidate-bundle"
            old_manifest = _make_release(old, "1.0.0", old_commit, "old-behavior")
            candidate_manifest = _make_release(
                candidate, "1.0.1", candidate_commit, "qa-candidate-change"
            )

            # Stub only environment bootstrapping; no package manager/network or
            # shortcut/PATH changes. Bundle extraction, integrity checks,
            # activation, child launch and rollback still use the suite code.
            with patch.object(suite, "create_venv", return_value=Path(sys.executable)), \
                    patch.object(suite, "install_pip"), \
                    patch.object(suite, "run", side_effect=_run_with_local_installer):
                suite.install(old, prefix, selected=["tthings"], shortcuts=False)
            settings = prefix / "user-data/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"fixture":"keep-me"}\n', encoding="utf-8")
            old_state = json.loads((prefix / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(old_state["version"], "1.0.0")

            archive = root / "candidate.zip"
            _archive(candidate, archive)
            feed_path = root / "local-suite-update.json"
            feed = {
                "schema_version": 1,
                "app_id": "ttools",
                "version": "1.0.1",
                "source_commit": candidate_commit,
                "artifacts": [{
                    "platform": dist.platform_id(),
                    "url": "https://local.invalid/candidate.zip",
                    "sha256": _sha256(archive),
                }],
            }
            feed_path.write_text(json.dumps(feed), encoding="utf-8")

            def local_feed():
                return json.loads(feed_path.read_text(encoding="utf-8"))

            def local_download(url, target, *_args):
                self.assertEqual(url, "https://local.invalid/candidate.zip")
                shutil.copyfile(archive, target)

            # A corrupt feed hash must leave the old release active and launchable.
            bad_feed = dict(feed)
            bad_feed["artifacts"] = [dict(feed["artifacts"][0], sha256="0" * 64)]
            feed_path.write_text(json.dumps(bad_feed), encoding="utf-8")
            with patch.object(suite, "create_venv", return_value=Path(sys.executable)), \
                    patch.object(suite, "install_pip"), \
                    patch.object(suite, "run", side_effect=_run_with_local_installer), \
                    patch.object(suite, "release_manifest", side_effect=local_feed), \
                    patch.object(suite, "fetch", side_effect=local_download):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    suite.update(prefix, force=True)
            state_after_failure = json.loads((prefix / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state_after_failure["version"], "1.0.0")
            self.assertEqual(
                _run_first_app(old_state),
                f"functional:1.0.0:{old_commit}:old-behavior",
            )

            # Restore the real local-feed digest and perform discovery through restart.
            feed_path.write_text(json.dumps(feed), encoding="utf-8")
            with patch.object(suite, "create_venv", return_value=Path(sys.executable)), \
                    patch.object(suite, "install_pip"), \
                    patch.object(suite, "run", side_effect=_run_with_local_installer), \
                    patch.object(suite, "release_manifest", side_effect=local_feed), \
                    patch.object(suite, "fetch", side_effect=local_download):
                self.assertTrue(suite.update(prefix, force=True))

            active = json.loads((prefix / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(active["version"], "1.0.1")
            active_release = Path(active["release"])
            installed_manifest = json.loads((active_release / "bundle.json").read_text())
            self.assertEqual(installed_manifest["source_commit"], candidate_commit)
            self.assertEqual(installed_manifest["files"], candidate_manifest["files"])
            self.assertEqual(
                _sha256(active_release / "components/versions.json"),
                candidate_manifest["files"]["components/versions.json"],
            )
            self.assertEqual(
                _run_first_app(active),
                f"functional:1.0.1:{candidate_commit}:qa-candidate-change",
            )
            self.assertEqual(settings.read_text(encoding="utf-8"), '{"fixture":"keep-me"}\n')

            suite.rollback(prefix)
            rolled_back = json.loads((prefix / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(rolled_back["version"], "1.0.0")
            self.assertEqual(
                _run_first_app(rolled_back),
                f"functional:1.0.0:{old_commit}:old-behavior",
            )
            self.assertEqual(settings.read_text(encoding="utf-8"), '{"fixture":"keep-me"}\n')


if __name__ == "__main__":
    unittest.main()
