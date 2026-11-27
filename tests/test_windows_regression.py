"""Windows regression tests: real launch commands, exit codes, locking, terminal restore.

These run on Windows; on other platforms the Windows-only checks are skipped.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WINDOWS = os.name == "nt" or sys.platform == "win32"
ROOT = Path(__file__).resolve().parents[1]
TSPOTIFY_SRC = ROOT / "components/tspotify/source/src"
TTHINGS_SRC = ROOT / "components/tthings/source"
TVPN_SRC = ROOT / "components/tvpn/source"


def run_py(args, *, cwd=None, env_extra=None, python=None, timeout=120):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TTOOLS_AUTOUPDATE"] = "0"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [python or sys.executable, *map(str, args)],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@unittest.skipUnless(WINDOWS, "Windows-only regression test")
class WindowsLaunchRegression(unittest.TestCase):
    def test_tspotify_verify_runtime_exit_zero(self):
        result = run_py(["-m", "tspotify", "verify-runtime"],
                        env_extra={"PYTHONPATH": str(TSPOTIFY_SRC)})
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform"], "Windows")

    def test_tspotify_doctor_exit_zero(self):
        result = run_py(["-m", "tspotify", "doctor"],
                        env_extra={"PYTHONPATH": str(TSPOTIFY_SRC)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tspotify doctor", result.stdout)

    def test_tspotify_demo_does_not_require_linux(self):
        # --demo needs a TTY for curses, but it must NOT fail early with
        # 'Managed ttools runtime currently supports Linux only'.
        try:
            result = run_py(["-m", "tspotify", "--demo"],
                            env_extra={"PYTHONPATH": str(TSPOTIFY_SRC)}, timeout=20)
            stderr, stdout = result.stderr, result.stdout
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        self.assertNotIn("currently supports Linux only", stderr)
        self.assertNotIn("currently supports Linux only", stdout)

    def test_tthings_doctor_exit_zero(self):
        result = run_py(["-m", "tthings", "--doctor"],
                        env_extra={"PYTHONPATH": str(TTHINGS_SRC)})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tthings_snapshot_exit_zero(self):
        result = run_py(["-m", "tthings", "--effect", "stars", "--snapshot", "64x18"],
                        env_extra={"PYTHONPATH": str(TTHINGS_SRC)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())

    def test_tvpn_manage_doctor_exit_zero(self):
        result = run_py([TVPN_SRC / "manage.py", "doctor"])
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["app_id"], "tvpn")
        self.assertIn("network_tested", payload)
        self.assertFalse(payload["network_tested"])

    def test_tvpn_manage_stop_not_running_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_py([TVPN_SRC / "manage.py", "--root", tmp, "stop", "--timeout", "1"])
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(WINDOWS, "Windows-only regression test")
class WindowsLockingRegression(unittest.TestCase):
    def test_tspotify_runtime_lock_is_reentrant_safe_and_releases(self):
        sys.path.insert(0, str(TSPOTIFY_SRC))
        try:
            from tspotify import managed
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TSPOTIFY_INSTALL_PREFIX"] = tmp
            try:
                with managed.runtime_lock():
                    # A second, non-blocking acquisition in-process must fail.
                    with self.assertRaises(RuntimeError):
                        with managed.runtime_lock():
                            pass
                # After release, it can be acquired again.
                with managed.runtime_lock():
                    pass
            finally:
                os.environ.pop("TSPOTIFY_INSTALL_PREFIX", None)

    def test_ttools_msvcrt_lock_releases(self):
        from ttools.distribution import locked
        with tempfile.TemporaryDirectory() as tmp:
            with locked(Path(tmp)):
                pass
            # Re-acquire after clean exit.
            with locked(Path(tmp)):
                pass


@unittest.skipUnless(WINDOWS, "Windows-only regression test")
class WindowsTerminalRegression(unittest.TestCase):
    def test_vt_key_mapping(self):
        sys.path.insert(0, str(TTHINGS_SRC))
        try:
            from tthings.terminal import _vt_key
        finally:
            sys.path.pop(0)
        self.assertEqual(_vt_key("\x1b[A"), "up")
        self.assertEqual(_vt_key("\x1b[B"), "down")
        self.assertEqual(_vt_key("\x1b[C"), "right")
        self.assertEqual(_vt_key("\x1b[D"), "left")
        self.assertEqual(_vt_key("\x1b[5~"), "pgup")
        self.assertEqual(_vt_key("\x1b[6~"), "pgdown")
        self.assertEqual(_vt_key("\x1b"), "escape")

    def test_terminal_start_stop_is_safe_without_console(self):
        sys.path.insert(0, str(TTHINGS_SRC))
        try:
            from tthings.terminal import Terminal
        finally:
            sys.path.pop(0)
        term = Terminal()
        term.start()
        term.stop()  # must restore and never raise
        self.assertFalse(term.active)
        term.stop()  # idempotent


class WindowsComponentSelection(unittest.TestCase):
    def test_windows_excludes_soundcloud(self):
        from ttools.suite import supported_components, default_components, WINDOWS_COMPONENTS
        if WINDOWS:
            self.assertNotIn("tsoundcloud", supported_components("windows-x86_64"))
            self.assertNotIn("tsoundcloud", default_components("windows-x86_64"))
            self.assertEqual(set(default_components("windows-x86_64")), set(WINDOWS_COMPONENTS))
        self.assertNotIn("tsoundcloud", supported_components("windows-x86_64"))
        self.assertIn("tsoundcloud", supported_components("linux-x86_64"))

    def test_tspotify_runtime_lock_module_imports_on_windows(self):
        sys.path.insert(0, str(TSPOTIFY_SRC))
        try:
            from tspotify import managed  # noqa: F401
        finally:
            sys.path.pop(0)


class LauncherIntegrationRegression(unittest.TestCase):
    """The launcher must find the bundled components and keep terminal transparency."""

    def test_dev_catalog_is_discovered_without_user_sources(self):
        import ttools.core as core
        dev = core._dev_catalog_path()
        self.assertIsNotNone(dev, "development apps.local.json was not discovered")
        old_config = core.CONFIG
        old_catalog = os.environ.pop("TTOOLS_CATALOG", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                core.CONFIG = Path(tmp)
                apps, errors = core.load_apps()
        finally:
            core.CONFIG = old_config
            if old_catalog is not None:
                os.environ["TTOOLS_CATALOG"] = old_catalog
        self.assertFalse(errors, errors)
        ids = {app["id"] for app in apps}
        self.assertTrue({"tspotify", "tthings", "ttelegram", "tvpn"}.issubset(ids),
                        f"launcher discovered only {sorted(ids)}")

    def test_launcher_keeps_terminal_transparent(self):
        source = (ROOT / "ttools/__main__.py").read_text(encoding="utf-8")
        self.assertNotIn("self.s.bkgd(", source,
                         "bkgd() paints an opaque window background over terminal transparency")
        self.assertIn("use_default_colors()", source)
        self.assertIn("except curses.error", source,
                      "use_default_colors() must be guarded on Windows PDCurses")


if __name__ == "__main__":
    unittest.main()
