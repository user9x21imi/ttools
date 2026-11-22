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
        raise RuntimeError("Managed ttools runtime currently supports Linux only")
    import fcntl

    with (root / "run.lock").open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("tspotify запущен или обновляется; дождитесь завершения") from None
        yield
