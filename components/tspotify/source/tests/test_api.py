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
                "next": "https://api.spotify.com/v1/playlists/p/items?offset=1",
            },
        )

    mock(api, handler)
    value = api.context("playlist", "p", "Private mix")
    assert [x["id"] for x in value["tracks"]] == ["a", "b"]
    assert value["context_uri"] == "spotify:playlist:p"
    assert api.context("playlist", "p", "Private mix") == value
    assert len(calls) == 2
    assert all("/playlists/p/items" in call for call in calls)


def test_artist_profile_fetches_full_catalog_by_group_and_paginates(api):
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith("/artists/a"):
            return httpx.Response(200, json={"id": "a", "name": "Artist", "images": [], "genres": []})
        if "include_groups=album" in url and "offset=10" not in url:
            return httpx.Response(200, json={
                "items": [{"id": "album-1", "name": "First", "album_type": "album"}],
                "next": "https://api.spotify.com/v1/artists/a/albums?include_groups=album&limit=10&offset=10",
            })
        if "include_groups=album" in url:
            return httpx.Response(200, json={"items": [{"id": "album-2", "name": "Second"}], "next": None})
        group = next(group for group in ("single", "appears_on", "compilation") if f"include_groups={group}" in url)
        return httpx.Response(200, json={"items": [{"id": group, "name": group}], "next": None})

    mock(api, handler)
    profile = api.artist_profile("a", "Artist")
    assert profile["artist"]["name"] == "Artist"
    assert [item["id"] for item in profile["releases"]["album"]] == ["album-1", "album-2"]
    assert all(profile["releases"][group] for group in ("single", "appears_on", "compilation"))
    assert not any("top-tracks" in call for call in calls)
    assert len(calls) == 6
    assert api.artist_profile("a", "Artist") == profile
    assert len(calls) == 6


def test_artist_profile_propagates_removed_or_denied_api_endpoint(api):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(404, json={"error": {"message": "not found"}})
    mock(api, handler)
    with pytest.raises(SpotifyError) as error:
        api.artist_profile("missing", "Missing")
    assert error.value.status == 404
    assert len(calls) == 1


def test_artist_profile_keeps_available_groups_when_one_group_is_denied(api):
    def handler(request):
        if request.url.path.endswith("/artists/a"):
            return httpx.Response(200, json={"id": "a", "name": "Artist"})
        group = request.url.params.get("include_groups")
        if group == "album":
            return httpx.Response(403, json={"error": {"message": "unavailable"}})
        return httpx.Response(200, json={"items": [{"id": group, "name": group}], "next": None})

    mock(api, handler)
    profile = api.artist_profile("a", "Artist")
    assert profile["unavailable_groups"] == {"album": 403}
    assert not profile["releases"]["album"]
    assert profile["releases"]["single"][0]["id"] == "single"


def test_artist_profile_respects_retry_after_instead_of_returning_fake_catalog(api):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/artists/a"):
            return httpx.Response(200, json={"id": "a", "name": "Artist"})
        return httpx.Response(429, headers={"Retry-After": "12"})

    mock(api, handler)
    with pytest.raises(RateLimited) as error:
        api.artist_profile("a", "Artist")
    assert error.value.seconds == 12
    assert len(calls) == 2


def test_artist_context_does_not_call_removed_top_tracks_endpoint(api):
    mock(api, lambda request: pytest.fail("removed endpoint must not be requested"))
    with pytest.raises(SpotifyError, match="популярных треков артиста удалён"):
        api.context("artist", "a", "Artist")


def test_search_uses_category_and_offset_pagination(api):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"artists": {
            "items": [{"id": "artist-2", "name": "Artist 2"}],
            "next": None,
            "offset": 10,
            "total": 11,
        }})
    mock(api, handler)
    result = api.search("Artist", "artist", 10)
    assert result["artists"][0]["id"] == "artist-2"
    assert result["_paging"]["artist"] == {"offset": 10, "total": 11, "next": None}
    assert "type=artist" in calls[0] and "limit=10" in calls[0] and "offset=10" in calls[0]


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


def test_new_releases_are_reported_as_removed_without_fake_albums(api):
    mock(api, lambda request: pytest.fail("removed browse endpoint must not be requested"))
    with pytest.raises(SpotifyError, match="удалил каталог новых релизов"):
        api.library("Новые релизы")


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
        api.library("Рекомендации")


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


def test_slow_remote_observation_never_blocks_native_playback_poll(api):
    import threading

    started, release = threading.Event(), threading.Event()
    track = {"id": "cached", "duration_ms": 180000}
    api.idle = False
    api.backend = SimpleNamespace(
        local_enabled=True,
        _volume_active=True,
        observe_connect=True,
        event={},
        playback=lambda _: {"item": track, "is_playing": True},
    )

    def slow_request(*args):
        started.set()
        release.wait(2)
        return {}

    api.request = slow_request
    try:
        before = time.monotonic()
        assert api.playback()["item"]["id"] == "cached"
        assert time.monotonic() - before < 0.1
        assert started.wait(0.5)
        before = time.monotonic()
        assert api.playback()["item"]["id"] == "cached"
        assert time.monotonic() - before < 0.1
    finally:
        release.set()


def test_known_playlist_metadata_avoids_track_lookup_when_skipping(api):
    track = {"id": "next", "duration_ms": 180000, "name": "Next"}
    api.remember_tracks({"tracks": [track]})
    api.backend = SimpleNamespace(
        event={}, playback=lambda _: {"_pending_track_id": "next", "is_playing": True}
    )
    api.request = lambda *a: pytest.fail("Known metadata must not hit the network")
    assert api.playback()["item"] == track


def test_transient_gateway_failure_retries_idempotent_play_once(api):
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(502 if len(calls) == 1 else 204)

    mock(api, respond)
    api.request("PUT", "me/player/play", {"uris": ["spotify:track:t"]})
    assert calls == ["PUT", "PUT"]


def test_gateway_failure_never_replays_non_idempotent_skip(api):
    calls = []
    mock(api, lambda request: calls.append(request.method) or httpx.Response(502))
    with pytest.raises(SpotifyError):
        api.request("POST", "me/player/next")
    assert calls == ["POST"]


def test_native_selected_track_load_avoids_web_api_and_device_discovery(api):
    calls = []
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_load=True,
        device_id="local",
        _events=lambda: None,
        load_track=lambda *args: calls.append(args),
        wait_playing=lambda *a, **kw: None,
        preferred_volume=0,
        muted=True,
    )
    api.request = lambda *a, **kw: pytest.fail("Native load must not call Web API")
    api.start({"id": "a" * 22, "duration_ms": 180000}, context_uri="spotify:playlist:p")
    assert calls == [("spotify:track:" + "a" * 22, "spotify:playlist:p", 0)]
    assert api.last_playback["is_playing"]


def test_native_load_passes_cached_queue_without_requesting_playlist(api):
    queue = ["spotify:track:" + "a" * 22, "spotify:track:" + "b" * 22]
    calls = []
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_load=True,
        local_queue=True,
        device_id="local",
        _events=lambda: None,
        load_track=lambda *args: calls.append(args),
        wait_playing=lambda *a, **kw: None,
        preferred_volume=0,
        muted=True,
    )
    api.request = lambda *a, **kw: pytest.fail("Cached queue must not use Web API")
    api.start({"id": "a" * 22, "duration_ms": 180000, "_queue_uris": queue})
    assert calls[0][3] == queue


def test_pre_activation_volume_is_applied_again_when_native_audio_becomes_active(api):
    active, actual, commands = [False], [0], []

    def control(command, value):
        commands.append((command, value))
        if active[0]:
            actual[0] = value

    api.idle = False
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_control=control,
        muted=False,
        unmute_after_user_volume=lambda _: None,
        event={},
        playback=lambda _: {"item": {"id": "t"}, "is_playing": True},
    )
    api.control("volume", 70)
    assert actual[0] == 0
    active[0] = True
    api.playback()
    assert actual[0] == 70
    api.playback()
    assert commands == [("volume", 70), ("volume", 70)]


@pytest.mark.parametrize(
    "command,initial,expected",
    [
        ("shuffle", False, 1),
        ("shuffle", True, 0),
        ("repeat", "off", 1),
        ("repeat", "context", 2),
        ("repeat", "track", 0),
    ],
)
def test_native_modes_do_not_call_web_api(api, monkeypatch, command, initial, expected):
    calls = []
    state = {
        "shuffle_state": initial if command == "shuffle" else False,
        "repeat_state": initial if command == "repeat" else "off",
    }
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_modes=True,
        playback=lambda fallback: dict(state),
        local_control=lambda *args: calls.append(args),
    )
    api.external = False
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(api, "request", lambda *a, **kw: pytest.fail("Native modes must not use Web API"))
    api.control(command)
    assert calls == [(command, expected)]


def test_play_at_queue_end_uses_native_restart_and_keeps_actual_queue(api, monkeypatch):
    calls = []
    item = {"id": "ended", "name": "Ended"}
    api.backend = SimpleNamespace(
        local_enabled=True,
        event={},
        local_control=lambda *args: calls.append(args),
        playback=lambda _: {"queue_ended": True, "item": item, "progress_ms": 400000, "is_playing": False},
    )
    api.idle = False
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(
        api, "start", lambda *a, **kw: pytest.fail("Do not replace native queue with saved album")
    )
    api.control("play-pause")
    assert calls == [("play",)]


def test_uncached_native_album_keeps_context_instead_of_single_track_queue(api, monkeypatch):
    calls = []
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_load=True,
        local_queue=True,
        _events=lambda: None,
        load_track=lambda *a: calls.append(a),
        wait_playing=lambda *a, **kw: None,
        device_id="native",
        event={},
        muted=True,
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(api, "activate_output_volume", lambda: None)
    api.start({"id": "a" * 22, "duration_ms": 180000}, context_uri="spotify:album:album")
    assert calls == [("spotify:track:" + "a" * 22, "spotify:album:album", 0)]


def test_jam_uses_native_session_and_returns_only_server_invitation(api, monkeypatch):
    calls = []
    api.backend = SimpleNamespace(
        local_enabled=True,
        native_jam=True,
        local_control=lambda *args: calls.append(args),
        request=lambda *args, **kwargs: {
            "jam": {
                "status": "ready",
                "url": "https://spotify.link/realInvite",
                "members": [{"name": "Host"}],
            }
        },
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(
        api, "request", lambda *a, **kw: pytest.fail("Do not use Web API or construct track URLs")
    )
    value = api.start_jam()
    assert calls == [("jam-start",)] and value["url"] == "https://spotify.link/realInvite"


def test_jam_server_rejection_is_not_reported_as_created(api, monkeypatch):
    api.backend = SimpleNamespace(
        local_enabled=True,
        native_jam=True,
        local_control=lambda *args: None,
        request=lambda *args, **kwargs: {"jam": {"status": "error", "message": "Forbidden"}},
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    with pytest.raises(SpotifyError, match="Forbidden"):
        api.start_jam()


@pytest.mark.parametrize("position,expected", [(180000, 0), (179500, 0), (12000, 12000)])
@pytest.mark.parametrize("legacy_duration", [False, True])
def test_restored_end_position_does_not_resume_final_millisecond(
    api, monkeypatch, position, expected, legacy_duration
):
    item = {
        "id": "a",
        **({"duration": {"secs": 180, "nanos": 0}} if legacy_duration else {"duration_ms": 180000}),
    }
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(api, "playback", lambda: {"item": item, "progress_ms": position})
    calls = []
    monkeypatch.setattr(api, "start", lambda *a, **kw: calls.append((a, kw)))
    api.control("play-pause")
    assert calls == [((item,), {"position_ms": expected})]


def test_next_from_restored_session_selects_actual_next_cached_track(api, monkeypatch):
    tracks = [{"id": "a", "type": "track"}, {"id": "b", "type": "track"}]
    api.remember_tracks(tracks)
    item = {"id": "a", "_queue_uris": ["spotify:track:a", "spotify:track:b"]}
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(api, "playback", lambda: {"item": item, "progress_ms": 180000})
    calls = []
    monkeypatch.setattr(api, "start", lambda *a, **kw: calls.append((a, kw)))
    api.control("next")
    assert calls[0][0][0]["id"] == "b" and calls[0][1]["position_ms"] == 0


def test_repeat_waits_through_intermediate_native_confirmation(api, monkeypatch):
    states = iter(
        [
            {"repeat_state": "context"},
            {"repeat_state": "track", "modes_pending": True},
            {"repeat_state": "track", "modes_pending": False},
        ]
    )
    calls = []
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_modes=True,
        native_snapshot={"queue_current_uri": "spotify:track:a"},
        local_control=lambda *args: calls.append(args),
        playback=lambda _: next(states),
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    assert "ожидает" not in api.control("repeat")
    assert calls == [("repeat", 2)]
    assert api.last_playback["repeat_state"] == "track"


def test_repeat_does_not_accept_old_snapshot_even_if_pending_flag_cleared(api, monkeypatch):
    states = iter(
        [
            {"repeat_state": "off"},
            {"repeat_state": "off", "modes_pending": False},
            {"repeat_state": "context", "modes_pending": False},
        ]
    )
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_modes=True,
        native_snapshot={"queue_current_uri": "spotify:track:a"},
        local_control=lambda *args: None,
        playback=lambda _: next(states),
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    api.control("repeat")
    assert api.last_playback["repeat_state"] == "context"


def test_atomic_modes_return_pending_target_without_waiting_for_streaming_loop(api, monkeypatch):
    states = iter([{"repeat_state": "off"}, {"repeat_state": "context", "modes_pending": True}])
    api.backend = SimpleNamespace(
        local_enabled=True,
        local_modes=True,
        atomic_modes=True,
        native_snapshot={"queue_current_uri": "spotify:track:a"},
        local_control=lambda *args: None,
        playback=lambda _: next(states),
    )
    monkeypatch.setattr(api, "ensure_engine", lambda: None)
    monkeypatch.setattr(
        time, "sleep", lambda _: pytest.fail("Atomic mode commands must not wait for native playback")
    )
    assert "ожидает" in api.control("repeat")
    assert api.last_playback["repeat_state"] == "context"
