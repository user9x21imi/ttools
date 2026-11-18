import json
import time
from types import SimpleNamespace

import httpx
import pytest

from tspotify import auth
from tspotify.api import RateLimited, Spotify, SpotifyError, track_from_entry


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(auth, "access_token", lambda: "test-only-token")
    value = Spotify()
    yield value
    value.close()


def mock(api, handler):
    api.http.close()
    api.http = httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "entry,valid",
    [
        (None, False),
        ({"track": None}, False),
        ({"track": {"id": "abc"}}, True),
        ({"item": {"id": "abc"}}, True),
        ({"id": "abc", "track": True}, True),
        ({"id": "abc", "is_local": True}, False),
        (True, False),
    ],
)
def test_new_and_old_spotify_track_schemas_are_normalized(entry, valid):
    value = track_from_entry(entry)
    assert bool(value) == valid
    if valid:
        assert isinstance(value, dict)


def test_playlist_follows_pagination_and_caches_complete_result(api):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "offset=1" in str(request.url):
            return httpx.Response(200, json={"items": [{"track": {"id": "b", "track": True}}], "next": None})
        return httpx.Response(
            200,
            json={
                "items": [{"track": {"id": "a"}}, {"track": None}],
                "next": "https://api.spotify.com/v1/playlists/p/tracks?offset=1",
            },
        )

    mock(api, handler)
    value = api.context("playlist", "p", "Private mix")
    assert [x["id"] for x in value["tracks"]] == ["a", "b"]
    assert value["context_uri"] == "spotify:playlist:p"
    assert api.context("playlist", "p", "Private mix") == value
    assert len(calls) == 2


def test_rate_limit_blocks_further_requests_instead_of_hammering_spotify(api):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "20"})

    mock(api, handler)
    with pytest.raises(RateLimited):
        api.request("GET", "me")
    with pytest.raises(RateLimited):
        api.request("PUT", "me/player/play")
    assert len(calls) == 1


def test_authorization_is_never_sent_to_other_hosts(api):
    mock(api, lambda request: pytest.fail("network must not be used"))
    with pytest.raises(ValueError):
        api.request("GET", "https://attacker.example/collect")


@pytest.mark.parametrize("saved,method,new_state", [(True, "DELETE", False), (False, "PUT", True)])
def test_favorite_toggle_uses_server_state_not_stale_local_cache(api, saved, method, new_state):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=[saved]) if request.method == "GET" else httpx.Response(204)

    mock(api, handler)
    assert api.toggle_favorite("track") is new_state
    assert calls == ["GET", method]


def test_track_start_preserves_playlist_context_and_waits_for_actual_playing(api):
    bodies = []
    mock(api, lambda req: bodies.append(json.loads(req.content)) or httpx.Response(204))
    waited = []
    api.device_id = "device"
    api.backend = SimpleNamespace(_events=lambda: None, wait_playing=lambda *a, **k: waited.append((a, k)))
    message = api.start({"id": "track", "name": "Song", "_context_uri": "spotify:playlist:mix"})
    assert bodies == [{"context_uri": "spotify:playlist:mix", "offset": {"uri": "spotify:track:track"}}]
    assert waited[0][0] == ("track",)
    assert "Song" in message


def test_accepted_request_is_not_misreported_as_success_if_audio_cannot_load(api):
    mock(api, lambda req: httpx.Response(204))
    api.device_id = "device"

    def failed(*args, **kwargs):
        raise RuntimeError("audio failed")

    api.backend = SimpleNamespace(_events=lambda: None, wait_playing=failed)
    with pytest.raises(RuntimeError, match="audio failed"):
        api.start({"id": "track"})


def test_auto_device_prefers_existing_logged_in_desktop_spotify(api):
    mock(
        api,
        lambda req: httpx.Response(
            200,
            json={
                "devices": [
                    {"id": "ours", "name": "tspotify", "is_active": False},
                    {"id": "desktop", "name": "My MacBook", "is_active": True},
                ]
            },
        ),
    )
    assert api.select_device()["id"] == "desktop"
    assert api.external and api.device_id == "desktop"


def test_integrated_preference_does_not_hijack_existing_device(api):
    mock(api, lambda req: httpx.Response(200, json={"devices": [{"id": "other", "name": "Desktop"}]}))
    assert api.select_device("integrated") is None
    assert not api.external


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_http_failures_are_visible_not_success_messages(api, status):
    mock(api, lambda req: httpx.Response(status, json={"error": {"message": "denied"}}))
    with pytest.raises((SpotifyError, auth.LoginRequired)):
        api.request("PUT", "me/player/play")


def test_control_volume_is_bounded(api):
    urls = []
    mock(api, lambda req: urls.append(str(req.url)) or httpx.Response(204))
    api.device_id = "test"
    api.control("volume", 140)
    api.control("volume", -10)
    assert "volume_percent=100" in urls[0] and "volume_percent=0" in urls[1]


def test_expired_rate_limit_allows_request(api):
    api.rate_until = time.monotonic() - 1
    mock(api, lambda req: httpx.Response(200, json={"ok": True}))
    assert api.request("GET", "me") == {"ok": True}


def test_first_play_waits_for_connect_device_registration(api, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(404, json={"error": {"message": "Device not found"}})
            if len(calls) == 1
            else httpx.Response(204)
        )

    mock(api, handler)
    monkeypatch.setattr("tspotify.api.time.sleep", lambda seconds: None)
    monkeypatch.setattr(api, "devices", lambda: [{"id": "device", "name": "tspotify"}])
    api.device_id = "device"
    api.backend = SimpleNamespace(_events=lambda: None, wait_playing=lambda *a, **k: None)
    assert "Воспроизводится" in api.start({"id": "track"})
    assert len(calls) == 3
    assert json.loads(calls[1].content) == {"device_ids": ["device"], "play": False}


def test_missing_connect_registration_restarts_engine_and_uses_new_device(api, monkeypatch):
    urls = []
    restarts = []

    def handler(request):
        urls.append(str(request.url))
        if "old-device" in str(request.url):
            return httpx.Response(404, json={"error": {"message": "Device not found"}})
        return httpx.Response(204)

    mock(api, handler)
    monkeypatch.setattr("tspotify.api.time.sleep", lambda seconds: None)
    backend = SimpleNamespace(device_id="old-device", _events=lambda: None, wait_playing=lambda *a, **k: None)

    def restart():
        restarts.append(True)
        backend.device_id = "new-device"

    backend.restart = restart
    api.backend = backend
    api.device_id = "old-device"
    monkeypatch.setattr(
        api, "devices", lambda: [] if not restarts else [{"id": "new-device", "name": "tspotify"}]
    )
    assert "Воспроизводится" in api.start({"id": "track"})
    assert restarts == [True]
    assert "old-device" in urls[0] and "new-device" in urls[-1]


def test_offline_external_device_is_not_replaced_by_unrequested_local_audio(api):
    mock(api, lambda request: httpx.Response(404, json={"error": {"message": "Device not found"}}))
    api.external = True
    api.device_id = "phone"
    with pytest.raises(SpotifyError):
        api.start({"id": "track"})


@pytest.mark.parametrize("body", [b"", b" \n", b"OK"])
def test_successful_commands_do_not_require_json_acknowledgement(api, body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body)

    mock(api, handler)
    assert api.request("PUT", "me/player/pause") is None
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"", b" \n", b"<html>gateway error</html>"])
def test_malformed_read_retries_once_then_reports_endpoint_without_raw_json_error(api, monkeypatch, body):
    monkeypatch.setattr("tspotify.api.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body)

    mock(api, handler)
    with pytest.raises(SpotifyError, match="некорректный ответ \\(me/player\\)"):
        api.request("GET", "me/player")
    assert len(calls) == 2


def test_transient_malformed_read_recovers_without_user_error(api, monkeypatch):
    monkeypatch.setattr("tspotify.api.time.sleep", lambda _: None)
    replies = iter([httpx.Response(200, content=b" "), httpx.Response(200, json={"devices": []})])
    mock(api, lambda request: next(replies))
    assert api.devices() == []


def test_no_active_player_204_is_normal(api):
    mock(api, lambda request: httpx.Response(204))
    assert api.request("GET", "me/player") is None


def test_corrupt_playlist_cache_is_refetched(api):
    from tspotify import paths

    (paths.CACHE / "playlist-p.json").write_text("", encoding="utf-8")
    mock(api, lambda request: httpx.Response(200, json={"items": [{"track": {"id": "a"}}]}))
    assert api.context("playlist", "p", "Playlist")["tracks"] == [{"id": "a"}]


def test_corrupt_library_cache_is_refetched(api):
    from tspotify import paths

    (paths.CACHE / "library-playlist.json").write_text(" ", encoding="utf-8")
    mock(api, lambda request: httpx.Response(200, json={"items": [{"id": "p"}]}))
    assert api.library("Плейлисты") == ("Плейлисты", [("playlist", {"id": "p"})])


def test_inactive_external_devices_are_not_auto_selected(api):
    mock(
        api,
        lambda request: httpx.Response(
            200, json={"devices": [{"id": "gone", "name": "Laptop", "is_active": False}]}
        ),
    )
    assert api.select_device("auto") is None
    assert not api.external


def test_volume_404_uses_recovery_before_retrying_command(api, monkeypatch):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return (
            httpx.Response(404, json={"error": {"message": "Device not found"}})
            if len(urls) == 1
            else httpx.Response(204)
        )

    mock(api, handler)
    api.device_id = "old"
    api.backend = SimpleNamespace(
        device_id="old",
        preferred_volume=0,
        _volume_set_at=0,
        _snapshot_time=0,
        unmute_after_user_volume=lambda v: None,
    )

    def recover(force=False):
        assert not force
        api.backend.device_id = "new"

    monkeypatch.setattr(api, "recover_device", recover)
    assert api.control("volume", 0) == "Громкость: 0%"
    assert "device_id=old" in urls[0] and "device_id=new" in urls[1]


def test_auto_external_disconnect_can_create_a_silent_owned_engine(api, monkeypatch):
    restarted = []
    backend = SimpleNamespace(
        device_id="new",
        muted=True,
        _events=lambda: None,
        wait_playing=lambda *a, **kw: None,
        restart=lambda: restarted.append(True),
    )
    api.backend_factory = lambda: backend
    api.device_id, api.external = "gone", True
    monkeypatch.setattr(api, "devices", lambda: [{"id": "new", "name": "tspotify"}])
    monkeypatch.setattr("tspotify.api.time.sleep", lambda _: None)
    mock(
        api,
        lambda request: (
            httpx.Response(404, json={"error": {"message": "Device not found"}})
            if "gone" in str(request.url)
            else httpx.Response(204)
        ),
    )
    assert "Воспроизводится" in api.start({"id": "t"})
    assert api.backend is backend and not api.external and restarted


def test_recent_history_keeps_contexts_and_unique_tracks(api):
    def handler(request):
        if "/recently-played" in str(request.url):
            entry = {"track": {"id": "t", "type": "track"}, "context": {"uri": "spotify:playlist:p"}}
            return httpx.Response(200, json={"items": [entry, entry]})
        return httpx.Response(200, json={"items": [{"id": "p", "name": "Recent playlist"}]})

    mock(api, handler)
    section, items = api.library("Недавние")
    assert section == "Недавние"
    assert [(kind, item["id"]) for kind, item in items] == [("playlist", "p"), ("track", "t")]


@pytest.mark.parametrize("section,expected", [("Ваши миксы", ["mix", "daily"]), ("Миксы дня", ["daily"])])
def test_mix_tabs_only_show_real_saved_spotify_mixes(api, section, expected):
    playlists = [
        {"id": "mix", "name": "Indie Mix", "owner": {"id": "spotify"}},
        {"id": "daily", "name": "Daily Mix 1", "owner": {"id": "spotify"}},
        {"id": "ordinary", "name": "Evening", "owner": {"id": "spotify"}},
        {"id": "fan", "name": "Daily Mix fake", "owner": {"id": "fan"}},
    ]
    mock(api, lambda request: httpx.Response(200, json={"items": playlists}))
    assert [item["id"] for _, item in api.library(section)[1]] == expected


def test_new_releases_are_openable_albums(api):
    mock(
        api,
        lambda request: httpx.Response(
            200, json={"albums": {"items": [{"id": "new", "name": "New release"}]}}
        ),
    )
    assert api.library("Новые релизы")[1] == [("album", {"id": "new", "name": "New release"})]


def test_recommendations_are_seeded_by_the_users_actual_top_tracks(api):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "/me/top/tracks" in str(request.url):
            return httpx.Response(200, json={"items": [{"id": "seed"}]})
        return httpx.Response(200, json={"tracks": [{"id": "recommended", "name": "For you"}]})

    mock(api, handler)
    assert api.library("Рекомендации")[1][0][1]["id"] == "recommended"
    assert "seed_tracks=seed" in calls[-1]


def test_restricted_discovery_is_not_substituted_with_fake_music(api):
    mock(api, lambda request: httpx.Response(403, json={"error": {"message": "unavailable"}}))
    with pytest.raises(SpotifyError, match="недоступен для этого входа"):
        api.library("Новые релизы")


def test_dead_engine_is_recovered_before_sending_playback_command(api, monkeypatch):
    calls = []
    backend = SimpleNamespace(
        alive=lambda: False, device_id="dead", _events=lambda: None, wait_playing=lambda *a, **kw: None
    )
    api.backend = backend

    def recover(force=False):
        assert force
        calls.append("recover")
        backend.alive = lambda: True
        backend.device_id = "new"

    monkeypatch.setattr(api, "recover_device", recover)
    mock(api, lambda request: calls.append(str(request.url)) or httpx.Response(204))
    api.start({"id": "t"})
    assert calls[0] == "recover" and "device_id=new" in calls[1]


def test_device_activation_uses_play_false_after_restart(api, monkeypatch):
    bodies = []
    backend = SimpleNamespace(device_id="new", restart=lambda: None)
    api.backend = backend
    api.device_id = "old"
    monkeypatch.setattr(api, "devices", lambda: [{"id": "new", "name": "tspotify"}])
    mock(api, lambda request: bodies.append(json.loads(request.content)) or httpx.Response(204))
    api.recover_device(force=True)
    assert bodies == [{"device_ids": ["new"], "play": False}]


def test_spotify_activation_restriction_is_retried_after_silent_transfer(api, monkeypatch):
    calls = []
    api.backend = SimpleNamespace(
        device_id="device", _events=lambda: None, wait_playing=lambda *a, **kw: None
    )

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                403, json={"error": {"message": "Player command failed: Restriction violated"}}
            )
        return httpx.Response(204)

    mock(api, handler)
    monkeypatch.setattr("tspotify.api.time.sleep", lambda _: None)
    api.start({"id": "track"})
    assert len(calls) == 3
    assert json.loads(calls[1].content) == {"device_ids": ["device"], "play": False}
    assert "/play?device_id=device" in str(calls[2].url)


def test_seek_uses_the_selected_device_and_clamps_negative_positions(api):
    urls = []
    api.device_id = "selected"
    mock(api, lambda request: urls.append(str(request.url)) or httpx.Response(204))
    api.control("seek", -100)
    assert "position_ms=0&device_id=selected" in urls[0]


def test_stale_device_snapshot_does_not_replace_recent_volume_change(api):
    api.idle = False
    api.device_id = "d"
    api.backend = SimpleNamespace(
        device_id="d",
        playback=lambda fallback: {"device": {"volume_percent": 20}},
        unmute_after_user_volume=lambda v: None,
    )
    mock(api, lambda request: httpx.Response(204))
    api.control("volume", 65)
    assert api.playback()["device"]["volume_percent"] == 65


def test_track_start_does_not_overwrite_new_user_volume_with_old_preference(api):
    calls = []
    mock(api, lambda request: calls.append(str(request.url)) or httpx.Response(204))
    api.backend = SimpleNamespace(
        device_id="d",
        muted=False,
        preferred_volume=35,
        _events=lambda: None,
        wait_playing=lambda *a, **kw: api.control("volume", 65),
        unmute_after_user_volume=lambda v: None,
    )
    api.start({"id": "t"})
    volumes = [url for url in calls if "/volume?" in url]
    assert len(volumes) == 1 and "volume_percent=65" in volumes[0]


def test_volume_limit_after_confirmed_playback_queues_restore_instead_of_failing_track(api):
    callbacks = []
    api.on_volume_retry = lambda *args: callbacks.append(args)
    api.backend = SimpleNamespace(
        device_id="d",
        preferred_volume=65,
        muted=False,
        _events=lambda: None,
        wait_playing=lambda *a, **kw: None,
    )
    mock(
        api,
        lambda request: (
            httpx.Response(429, headers={"Retry-After": "12"})
            if "/volume?" in str(request.url)
            else httpx.Response(204)
        ),
    )
    assert "Воспроизводится" in api.start({"id": "track"})
    assert callbacks == [(65, 12, 0)]


def test_fractional_retry_after_rounds_up_and_cannot_shorten_existing_backoff(api):
    mock(api, lambda request: httpx.Response(429, headers={"Retry-After": "1.2"}))
    with pytest.raises(RateLimited) as error:
        api.request("PUT", "me/player/volume")
    assert error.value.seconds == 2
    until = api.rate_until
    with pytest.raises(RateLimited):
        api.request("PUT", "me/player/volume")
    assert api.rate_until == until


def test_native_volume_does_not_call_web_api_even_during_rate_limit(api):
    calls = []
    api.rate_until = time.monotonic() + 60
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_control=lambda *args: calls.append(args),
        unmute_after_user_volume=lambda _: None,
    )
    api.request = lambda *args: pytest.fail("Native volume must not use Web API")
    assert api.control("volume", 75) == "Громкость: 75%"
    assert calls == [("volume", 75)]
    assert api.current_volume == 75
    assert api.resume_data["volume"] == 75
