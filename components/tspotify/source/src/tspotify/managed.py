"""Installation ownership shared by the native client and the ttools installer."""

import contextlib
import json
import os
from pathlib import Path
import sys


def prefix():
    value = os.environ.get("TSPOTIFY_INSTALL_PREFIX")
    if not value and getattr(sys, "frozen", False):
        try:
            value = json.loads(
                (Path(sys.executable).parent / ".ttools-managed.json").read_text(encoding="utf-8")
            ).get("prefix")
        except (OSError, ValueError, AttributeError):
            pass
    return Path(value).expanduser().resolve() if value else None


def owner():
    return "ttools" if prefix() else None


@contextlib.contextmanager
def runtime_lock():
    root = prefix()
    if root is None:
        yield
        return
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "run.lock"
    with lock_path.open("a+b") as stream:
        _acquire_exclusive(stream)
        try:
            yield
        finally:
            _release(stream)


def _acquire_exclusive(stream):
    """Take a non-blocking exclusive lock on one byte; raise RuntimeError if held."""
    try:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        raise RuntimeError("tspotify запущен или обновляется; дождитесь завершения") from None


def _release(stream):
    try:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_UN)
    except OSError:
        pass
