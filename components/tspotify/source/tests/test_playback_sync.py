import time
from types import SimpleNamespace

import httpx

from tspotify.api import Spotify
from tspotify.backend import Backend


def test_phone_selection_supersedes_saved_session_without_writing_to_spotify(monkeypatch):
    from tspotify import auth

    monkeypatch.setattr(auth, "access_token", lambda: "test")
    api = Spotify()
    api.last_playback = {"item": {"id": "old", "duration_ms": 100000}, "progress_ms": 99000}
    selected = {
        "item": {"id": "phone-selected", "duration_ms": 200000},
        "progress_ms": 1000,
        "is_playing": True,
    }
    api.backend = SimpleNamespace(
        event={"at": time.monotonic() + 1, "playing": True},
        playback=lambda fallback: dict(selected),
    )
    api.http.close()
    api.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(AssertionError("Unexpected network write/read"))
        )
    )
    try:
        assert api.playback()["item"]["id"] == "phone-selected"
        assert not api.idle
    finally:
        api.close()


def test_new_native_event_never_attaches_new_position_to_old_track():
    backend = Backend()
    backend._snapshot_time = time.monotonic()
    backend._base = {"item": {"id": "old", "duration_ms": 1000}, "progress_ms": 990}
    backend.event = {"track_id": "new", "position": 2000, "playing": True, "at": time.monotonic()}
    value = backend.playback({})
    assert value["item"] is None
    assert value["_pending_track_id"] == "new"
    assert value["progress_ms"] >= 2000


def test_remote_connect_target_is_not_overwritten_by_local_device():
    api = Spotify()
    try:
        api.external = True
        api.device_id = "phone"
        api.backend = SimpleNamespace(device_id="local")
        assert api.device_query() == "device_id=phone"
    finally:
        api.close()


def test_remote_observation_follows_phone_without_play_or_transfer_requests(monkeypatch):
    from tspotify import auth

    monkeypatch.setattr(auth, "access_token", lambda: "test")
    api = Spotify()
    calls = []
    api.backend = SimpleNamespace(observe_connect=True, device_id="local")
    api.http.close()

    def respond(request):
        calls.append(request.method)
        return httpx.Response(
            200, json={"device": {"id": "phone"}, "item": {"id": "selected"}, "is_playing": True}
        )

    api.http = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        assert api.playback()["item"]["id"] == "selected"
        assert api.external and api.device_id == "phone"
        assert calls == ["GET"]
    finally:
        api.close()


def test_stale_native_event_cannot_undo_fresh_phone_selection():
    backend = Backend()
    backend._snapshot_time = time.monotonic()
    backend._base = {"item": {"id": "previous"}}
    backend.event = {"track_id": "previous", "position": 150000, "playing": True, "at": time.monotonic() - 5}
    phone = {"item": {"id": "selected"}, "progress_ms": 0, "_observed_at": time.monotonic()}
    assert backend.playback(phone)["item"]["id"] == "selected"


def test_old_tspotify_device_from_web_api_cannot_replace_current_native_engine(monkeypatch):
    from tspotify import auth

    monkeypatch.setattr(auth, "access_token", lambda: "test")
    api = Spotify()
    api.idle = False
    api.backend = SimpleNamespace(
        observe_connect=True,
        device_id="current",
        event={},
        playback=lambda _: {"item": {"id": "actual"}, "is_playing": True},
    )
    api.http.close()
    api.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "device": {"id": "old", "name": "tspotify", "is_active": True},
                    "item": {"id": "stale"},
                    "is_playing": False,
                },
            )
        )
    )
    try:
        assert api.playback()["item"]["id"] == "actual"
        assert not api.external
        assert api.device_id != "old"
    finally:
        api.close()
