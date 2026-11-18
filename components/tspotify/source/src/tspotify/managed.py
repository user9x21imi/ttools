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
    if os.name != "posix":
        # ttools distribution adaptation: match the suite's Windows locking API.
        import msvcrt
        with (root / "run.lock").open("a+b") as stream:
            stream.seek(0); stream.write(b"0"); stream.flush(); stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("tspotify is running or updating") from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    with (root / "run.lock").open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("tspotify запущен или обновляется; дождитесь завершения") from None
        yield
