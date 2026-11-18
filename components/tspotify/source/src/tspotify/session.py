"""Private, validated session preferences; tests and demos must not overwrite them."""

import json
import threading

from . import paths

_lock = threading.RLock()


def load():
    try:
        value = json.loads((paths.CONFIG / "session.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            value = {}
    except (OSError, ValueError):
        value = {}
    volume = value.get("volume", 35)
    if type(volume) is not int or not 0 <= volume <= 100:
        volume = 35
    unmuted = value.get("unmuted_volume", volume or 35)
    if type(unmuted) is not int or not 1 <= unmuted <= 100:
        unmuted = volume or 35
    track = value.get("track")
    if not isinstance(track, dict) or not isinstance(track.get("id"), str):
        track = None
    position = value.get("position_ms", 0)
    if type(position) is not int or not 0 <= position <= 86400000:
        position = 0
    view = value.get("view")
    if not isinstance(view, dict):
        view = {}
    return {
        "volume": volume,
        "unmuted_volume": unmuted,
        "track": track,
        "position_ms": position,
        "view": view,
    }


def save(**changes):
    with _lock:
        value = load()
        value.update({key: data for key, data in changes.items() if key in value})
        paths.private_json(paths.CONFIG / "session.json", value)
        return value
