import json
import os
from pathlib import Path
import tempfile


def directory():
    base = os.environ.get("TSOUND_HOME")
    if base:
        return Path(base)
    base = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_CONFIG_HOME")
    return Path(base or Path.home() / ".config") / "tsound"


def read(name):
    try:
        return json.loads((directory() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write(name, data):
    folder = directory()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        Path(filename).replace(folder / name)
    finally:
        Path(filename).unlink(missing_ok=True)
