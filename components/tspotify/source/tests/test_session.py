import json
from types import SimpleNamespace

import httpx
import pytest

from tspotify import paths, session
from tspotify.api import Spotify
from tspotify.backend import Backend


def test_saved_session_survives_a_new_client_without_starting_music():
    track = {"id": "t", "name": "Трек", "duration_ms": 180000, "_context_uri": "spotify:playlist:p"}
    session.save(volume=65, track=track, position_ms=42000, view={"section": "Playlist", "selected_id": "t"})
    api = Spotify()
    try:
        assert api.current_volume == 65
        value = api.playback()
        assert value["item"] == track and value["progress_ms"] == 42000
        assert value["is_playing"] is False
        assert value["device"]["volume_percent"] == 65
        assert Backend().preferred_volume == 65
    finally:
        api.close()


def test_muted_test_run_never_overwrites_normal_session():
    session.save(volume=65, track={"id": "saved"}, position_ms=42000)
    before = (paths.CONFIG / "session.json").read_bytes()
    api = Spotify()
    api.session_muted = True
    try:
        assert api.current_volume == 0
        assert api.playback()["device"]["volume_percent"] == 0
        api.save_session({"item": {"id": "test"}, "progress_ms": 1}, volume=0)
        assert (paths.CONFIG / "session.json").read_bytes() == before
        assert Backend(muted=True).preferred_volume == 0
    finally:
        api.close()


@pytest.mark.parametrize(
    "data", ["", "{broken", "[]", '{"volume":500,"position_ms":"bad","view":[]}', '{"volume":true}']
)
def test_invalid_session_falls_back_to_safe_defaults(data):
    (paths.CONFIG / "session.json").write_text(data, encoding="utf-8")
    value = session.load()
    assert value["volume"] == 35 and value["position_ms"] == 0
    assert value["view"] == {}


def test_resume_starts_saved_track_at_saved_position_only_after_explicit_play(monkeypatch):
    from tspotify import auth

    session.save(
        volume=65,
        track={"id": "saved", "duration_ms": 180000, "_context_uri": "spotify:playlist:p"},
        position_ms=42000,
    )
    api = Spotify()
    api.http.close()
    calls = []
    api.http = httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(204))
    )
    api.backend = SimpleNamespace(
        device_id="d",
        muted=False,
        preferred_volume=65,
        _events=lambda: None,
        wait_playing=lambda *a, **kw: None,
        unmute_after_user_volume=lambda v: None,
    )
    monkeypatch.setattr(auth, "access_token", lambda: "test-token")
    try:
        assert api.playback()["is_playing"] is False and not calls
        api.control("play-pause")
        play = next(call for call in calls if "/play?" in str(call.url))
        assert json.loads(play.content) == {
            "context_uri": "spotify:playlist:p",
            "offset": {"uri": "spotify:track:saved"},
            "position_ms": 42000,
        }
        assert any("volume_percent=65" in str(call.url) for call in calls)
        assert not api.idle
    finally:
        api.close()


def test_volume_zero_is_preserved_as_an_intentional_choice():
    session.save(volume=0, unmuted_volume=55)
    assert Backend().preferred_volume == 0
    assert session.load()["unmuted_volume"] == 55


def test_boot_device_zero_never_replaces_saved_volume():
    session.save(volume=70, track={"id": "saved"}, position_ms=12000)
    api = Spotify()
    api.backend = SimpleNamespace(
        playback=lambda fallback: {"item": {"id": "saved"}, "device": {"volume_percent": 0}}, event={}
    )
    try:
        assert api.playback()["device"]["volume_percent"] == 70
        assert session.load()["volume"] == 70
    finally:
        api.close()
