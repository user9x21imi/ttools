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

    lock_path = root / "run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "posix":
        import fcntl

        with lock_path.open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("tspotify запущен или обновляется; дождитесь завершения") from None
            yield
    else:
        # Windows: use msvcrt.locking on a single byte at the start of the file.
        import msvcrt

        # Open in binary mode, create if needed. We keep the handle open for the
        # duration of the context manager; closing it releases the lock.
        # Use "a+b" to create the file if it doesn't exist, then seek to 0.
        stream = lock_path.open("a+b")
        lock_acquired = False
        try:
            # Lock the first byte (non-blocking). On Windows, msvcrt.locking
            # locks a specific byte range; we use 1 byte at offset 0.
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                lock_acquired = True
            except OSError:
                # errno 13 (EACCES) or errno 33 (EEXIST) on some Windows versions
                # indicate the lock is held by another process.
                raise RuntimeError("tspotify запущен или обновляется; дождитесь завершения") from None
            yield
        finally:
            # Unlock and close. msvcrt.LK_UNLCK releases the lock on the range.
            if lock_acquired:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            stream.close()
