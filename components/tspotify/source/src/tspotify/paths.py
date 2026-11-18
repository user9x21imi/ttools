"""OS-specific private state. Nothing here belongs in release artifacts."""

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

HOME = Path.home()
DATA = Path(os.environ.get("TSPOTIFY_DATA_DIR", user_data_dir("tspotify", appauthor=False)))
CACHE = Path(os.environ.get("TSPOTIFY_CACHE_DIR", user_cache_dir("tspotify", appauthor=False)))
CONFIG = Path(os.environ.get("TSPOTIFY_CONFIG_DIR", user_config_dir("tspotify", appauthor=False)))
BACKEND_CONFIG = CONFIG / "player"
# Reuse an existing login on Linux; do not copy credentials into the source tree.
legacy = HOME / ".cache/spotify-player"
BACKEND_CACHE = legacy if legacy.is_dir() and not os.environ.get("TSPOTIFY_DATA_DIR") else DATA / "player"
PORT = int(os.environ.get("TSPOTIFY_PORT", "39817"))
TOKEN_FILE = BACKEND_CACHE / "d420a117a32841c2b3474932e49fb54b_token.json"


def prepare():
    for path in (DATA, CACHE, CONFIG, BACKEND_CONFIG, BACKEND_CACHE):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)


def private_json(path, data):
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)
