import curses
import time
from types import SimpleNamespace

import pytest

from tspotify import paths, ui


class Window:
    def __init__(self, height=48, width=140):
        self.size = height, width
        self.calls = []

    def getmaxyx(self):
        return self.size

    def addnstr(self, y, x, text, limit, style=0):
        assert 0 <= y < self.size[0] and 0 <= x < self.size[1]
        self.calls.append((y, x, str(text)[:limit]))

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@pytest.fixture
def app(monkeypatch):
    for name in ("start_color", "use_default_colors", "init_pair", "curs_set"):
        monkeypatch.setattr(curses, name, lambda *args: None)
    monkeypatch.setattr(curses, "has_colors", lambda: True)
    monkeypatch.setattr(curses, "color_pair", lambda x: x)
    monkeypatch.setattr(curses, "COLORS", 256, raising=False)
    monkeypatch.setattr(curses, "COLOR_PAIRS", 65536, raising=False)
    monkeypatch.setattr(ui, "VOLUME_DEBOUNCE", 0.0)
    monkeypatch.setattr(ui, "VOLUME_INTERVAL", 0.0)
    monkeypatch.setattr(ui, "ART", paths.CACHE)
    monkeypatch.setattr(ui, "CONFIG", paths.CONFIG / "layout.json")
    monkeypatch.setattr(ui, "ASCII_ONLY", False)
    monkeypatch.setattr(
        ui,
        "Audio",
        lambda **kwargs: SimpleNamespace(bars=[0.0] * 32, enabled=True, status="test", close=lambda: None),
    )
    track = {"id": "t", "name": "Track", "type": "track", "track": True, "artists": [{"name": "Artist"}]}

    def cached(name, default):
        return {
            "Playlists": [{"Playlist": {"id": "p", "name": "Playlist"}}],
            "SavedAlbums": [{"id": "a", "name": "Album"}],
            "SavedTracks": {"spotify:track:t": track},
        }.get(name, default)

    monkeypatch.setattr(ui, "cached", cached)
    calls = []

    def record(name, result=None):
        def fn(*args):
            calls.append((name, args))
            return result

        return fn

    fake = SimpleNamespace(
        start=record("start", "playing"),
        start_context=record("start_context", "playing"),
        control=record("control", "done"),
        context=record("context", {"name": "Mix", "tracks": [track], "context_uri": "spotify:playlist:p"}),
        toggle_favorite=record("favorite", False),
        library=lambda section: (
            section,
            [("playlist", {"id": "p", "name": "Playlist"})]
            if section == "Плейлисты"
            else [("album", {"id": "a", "name": "Album"})],
        ),
        search=record("search", {"tracks": [track]}),
        backend=SimpleNamespace(restart=lambda: True),
        playback=lambda: {"item": track, "device": {"volume_percent": 0}},
    )
    monkeypatch.setattr(ui, "API", fake)
    monkeypatch.setattr(ui, "thumbnail", lambda *args: [[(80, 180, 100)] * 24 for _ in range(24)])
    value = ui.App(Window())
    value.playback = {"item": track, "device": {"volume_percent": 0}}
    value.test_calls = calls
    yield value
    value.transport_pool.shutdown(wait=True, cancel_futures=True)
    value.pool.shutdown(wait=True, cancel_futures=True)
    value.art_pool.shutdown(wait=True, cancel_futures=True)
    value.cover_pool.shutdown(wait=True, cancel_futures=True)


def settle(app):
    for _ in range(100):
        app.drain()
        if not app.pending and not app.volume_dirty:
            return
        time.sleep(0.002)
    pytest.fail("background UI work did not settle")


def test_enter_opens_playlist_then_plays_selected_track_in_context(app):
    app.key("\n")
    settle(app)
    assert app.section == "Mix" and app.items[0][0] == "track"
    assert isinstance(app.items[0][1], dict)  # Spotify's track:true must not become a boolean row.
    app.key("\n")
    settle(app)
    assert app.test_calls[-1][0] == "start"
    assert app.test_calls[-1][1][0]["_context_uri"] == "spotify:playlist:p"


def test_back_restores_library_selection(app):
    app.key("\n")
    settle(app)
    app.key(curses.KEY_LEFT)
    assert app.section == "Плейлисты" and app.items[0][0] == "playlist"


def test_search_focus_unicode_query_and_results(app):
    app.key("/")
    app.key("Музыка")
    app.key("\n")
    settle(app)
    assert app.test_calls[-1] == ("search", ("Музыка",))
    assert app.items[0][0] == "track"
    app.key("\t")
    assert app.editing
    app.key("\x1b")
    assert not app.editing


@pytest.mark.parametrize(
    "key,command", [(" ", "play-pause"), ("n", "next"), ("p", "previous"), ("s", "shuffle"), ("r", "repeat")]
)
def test_playback_keys_route_to_checked_control(app, key, command):
    app.key(key)
    settle(app)
    assert app.test_calls[-1] == ("control", (command, None))


def test_volume_limits_mute_and_restore(app):
    app.volume = 0
    app.key("-")
    settle(app)
    assert not app.test_calls
    app.volume = 100
    app.key("+")
    settle(app)
    assert not app.test_calls
    app.volume = 40
    app.volume_applied = 40
    app.key("m")
    settle(app)
    app.key("m")
    settle(app)
    assert app.volume == 40


def test_favorite_button_uses_server_confirmed_toggle(app):
    app.key("f")
    settle(app)
    assert app.test_calls[-1] == ("favorite", ("t",))
    assert "spotify:track:t" not in app.saved_tracks


def test_non_ascii_favorite_names_are_saved_as_utf8(app, monkeypatch):
    import json

    app.playback["item"]["name"] = "Тихая музыка"
    monkeypatch.setattr(ui.API, "toggle_favorite", lambda *args: True)
    app.key("f")
    settle(app)
    value = json.loads((ui.ART / "favorites.json").read_text(encoding="utf-8"))
    assert value["spotify:track:t"]["name"] == "Тихая музыка"


@pytest.mark.parametrize("key,section", [("1", "Плейлисты"), ("2", "Любимые"), ("3", "Альбомы")])
def test_library_tabs(app, key, section):
    app.key(key)
    assert app.section == section and app.items


def test_layout_reorder_cover_side_and_saving(app):
    app.key("L")
    app.key("J")
    app.key("c")
    app.key("\n")
    assert app.order[0] == "player" and app.cover_right and not app.layout_editor
    assert ui.CONFIG.exists()


def test_help_and_exit(app):
    app.key("?")
    assert app.help
    app.key("\x1b")
    assert not app.help
    app.key(curses.KEY_F1)
    assert app.help
    app.key("?")
    app.key("q")
    assert not app.running


def test_full_playlist_shortcut_preserves_selected_item(app):
    app.key("P")
    settle(app)
    assert app.test_calls[-1][0] == "start_context"
    assert app.test_calls[-1][1][0] == "playlist"


def test_command_failure_is_displayed_instead_of_success(app, monkeypatch):
    def fail(*args):
        raise RuntimeError("test network failure")

    monkeypatch.setattr(ui.API, "control", fail)
    app.key(" ")
    settle(app)
    assert "test network failure" in app.notice


def test_hiding_spectrum_and_cover_style_toggle(app):
    app.key("L")
    app.key("v")
    app.key("\n")
    assert not app.show_spectrum
    original = app.art_mode
    app.key("a")
    assert app.art_mode != original


@pytest.mark.parametrize(
    "height,width", [(24, 80), (25, 78), (30, 78), (40, 100), (48, 140), (80, 160), (18, 60)]
)
def test_layout_and_live_animation_survive_terminal_resize(app, height, width):
    app.render()
    settle(app)
    app.s.size = (height, width)
    app.render()
    app.animate()


def test_thumbnail_jobs_only_fetch_visible_items_once(app):
    app.render()
    settle(app)
    assert app.thumbnails.get("playlist:p")
    before = len(app.thumbnails)
    app.render()
    settle(app)
    assert len(app.thumbnails) == before


def test_ascii_font_fallback_uses_ascii_art_and_box_characters(app, monkeypatch):
    monkeypatch.setattr(ui, "ASCII_ONLY", True)
    app.art_mode = "ascii"
    app.render()
    assert any("+" in text for _, _, text in app.s.calls)


def test_spectrum_interpolates_instead_of_jumping_to_new_target(app):
    app.audio.bars = [1.0] * 32
    app.smooth_time = time.monotonic() - 0.03
    app.spectrum(1, 1, 4, 100)
    assert 0 < app.smooth_bars[0] < 0.5
    old = app.smooth_bars[0]
    app.audio.bars = [0.0] * 32
    app.smooth_time = time.monotonic() - 0.03
    app.spectrum(1, 1, 4, 100)
    assert old * 0.8 < app.smooth_bars[0] < old


def test_private_playlist_cover_uses_authenticated_library_image_url(app, monkeypatch):
    calls = []
    monkeypatch.setattr(ui, "cover", lambda url, *args: calls.append(url) or [[(1, 2, 3)]])
    monkeypatch.setattr(
        ui, "thumbnail", lambda *args: pytest.fail("public oEmbed not needed for private artwork")
    )
    app.load_thumbnail("playlist", {"id": "private", "images": [{"url": "https://i.scdn.co/image/private"}]})
    assert calls == ["https://i.scdn.co/image/private"]


def test_library_refresh_clamps_selection_when_remote_list_shrinks(app):
    settle(app)
    app.items = [("playlist", {"id": "p", "name": "One"}), ("playlist", {"id": "gone", "name": "Removed"})]
    app.selected = 1
    app.events.put(("library:Плейлисты", ("Плейлисты", [("playlist", {"id": "p", "name": "One"})]), None))
    app.drain()
    assert app.selected == 0
    app.key("\n")
    settle(app)


@pytest.mark.parametrize(
    "key,expected",
    [
        (curses.KEY_F10, 0),
        (curses.KEY_F11, 35),
        (curses.KEY_F12, 45),
    ],
)
@pytest.mark.parametrize("mode", ["normal", "editing", "help", "layout_editor"])
def test_function_volume_keys_work_in_all_input_modes(app, key, expected, mode):
    app.volume = 40
    app.volume_applied = 40
    if mode != "normal":
        setattr(app, mode, True)
    app.query = "keep search"
    app.key(key)
    settle(app)
    assert app.volume == expected
    assert app.test_calls[-1] == ("control", ("volume", str(expected)))
    assert app.query == "keep search"
    if mode != "normal":
        assert getattr(app, mode)


@pytest.mark.parametrize(
    "key,section",
    [
        ("4", "Недавние"),
        ("5", "Ваши миксы"),
        ("6", "Новые релизы"),
        ("7", "Рекомендации"),
        ("8", "Миксы дня"),
    ],
)
def test_discovery_sections_are_available_from_number_keys(app, key, section):
    app.key(key)
    settle(app)
    assert app.section == section


@pytest.mark.parametrize("size", [(24, 80), (48, 140), (70, 180)])
def test_fullscreen_artwork_metadata_spectrum_and_return(app, size):
    app.s.size = size
    selected = app.selected
    app.key(curses.KEY_F3)
    assert app.fullscreen
    app.art = [[(150, 180, 200)] * 32 for _ in range(32)]
    app.render()
    assert any("NOW PLAYING" in text for _, _, text in app.s.calls)
    assert any("Track" in text for _, _, text in app.s.calls)
    assert app.spectrum_area[2] > 0
    app.animate()
    app.key("\x1b")
    assert not app.fullscreen and app.selected == selected


def mouse_at(app, monkeypatch, x, y, state):
    monkeypatch.setattr(curses, "getmouse", lambda: (0, x, y, 0, state))
    app.key(curses.KEY_MOUSE)


def test_single_click_opens_playlist_and_following_double_event_does_not_play_track(app, monkeypatch):
    app.render()
    y, x, _, _, _, _ = next(hit for hit in app.hits if hit[4] == "row")
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    assert app.selected == 0
    settle(app)
    assert [call[0] for call in app.test_calls] == ["context"]
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_DOUBLE_CLICKED)
    settle(app)
    assert [call[0] for call in app.test_calls] == ["context"]


def test_mouse_can_open_discovery_tab_and_expand_player(app, monkeypatch):
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("key", "4"))
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    settle(app)
    assert app.section == "Недавние"
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("key", curses.KEY_F3))
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    assert app.fullscreen


def test_mouse_hover_focuses_panel_without_starting_audio(app, monkeypatch):
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("panel", "search"))
    mouse_at(app, monkeypatch, x + 1, y + 1, curses.REPORT_MOUSE_POSITION)
    assert app.focus_panel == "search"
    assert not app.test_calls


def test_mouse_volume_bar_can_set_zero_without_playing(app, monkeypatch):
    app.volume = app.volume_applied = 40
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4] == "volume")
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    settle(app)
    assert app.test_calls[-1] == ("control", ("volume", "0"))


def test_help_can_scroll_in_compact_terminal(app):
    app.s.size = (24, 80)
    app.help = True
    app.render()
    app.key(curses.KEY_DOWN)
    app.render()
    assert app.help_offset == 1


def click_key(app, monkeypatch, key):
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("key", key))
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    settle(app)


def test_single_click_plays_the_actual_clicked_track(app, monkeypatch):
    app.items = [("track", {"id": "first", "name": "First"}), ("track", {"id": "second", "name": "Second"})]
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("row", 1))
    mouse_at(app, monkeypatch, x + 8, y, curses.BUTTON1_CLICKED)
    settle(app)
    assert app.test_calls[-1] == ("start", ({"id": "second", "name": "Second"},))


@pytest.mark.parametrize("size", [(24, 80), (48, 140)])
@pytest.mark.parametrize(
    "key,command,value",
    [
        ("+", "volume", "45"),
        ("-", "volume", "35"),
        (" ", "play-pause", None),
        ("n", "next", None),
        ("p", "previous", None),
    ],
)
def test_visible_transport_buttons_work_while_search_has_focus(app, monkeypatch, size, key, command, value):
    app.s.size = size
    app.volume = 40
    app.editing = True
    app.query = "unchanged"
    app.render()
    click_key(app, monkeypatch, key)
    assert app.test_calls[-1] == ("control", (command, value))
    assert app.query == "unchanged"


def test_footer_enter_opens_playlist_and_search_button_focuses_search(app, monkeypatch):
    app.render()
    click_key(app, monkeypatch, "\n")
    assert app.test_calls[-1][0] == "context"
    app.render()
    click_key(app, monkeypatch, "/")
    assert app.editing


def test_layout_buttons_select_move_and_save_without_keyboard(app, monkeypatch):
    app.key("L")
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4:] == ("layout_row", 0))
    mouse_at(app, monkeypatch, x, y, curses.BUTTON1_CLICKED)
    first = app.order[0]
    click_key(app, monkeypatch, "J")
    assert app.order[1] == first
    app.render()
    click_key(app, monkeypatch, "\n")
    assert not app.layout_editor and ui.CONFIG.exists()


def test_help_buttons_scroll_and_close_without_clicking_underlying_controls(app, monkeypatch):
    app.s.size = (24, 80)
    app.key("?")
    app.render()
    click_key(app, monkeypatch, curses.KEY_DOWN)
    assert app.help_offset == 1 and app.help
    app.render()
    click_key(app, monkeypatch, "\x1b")
    assert not app.help and not app.test_calls


def test_hover_and_wheel_never_activate_tracks(app, monkeypatch):
    app.items = [("track", {"id": str(i), "name": str(i)}) for i in range(10)]
    app.render()
    y, x, *_ = next(hit for hit in app.hits if hit[4] == "row")
    mouse_at(app, monkeypatch, x, y, curses.REPORT_MOUSE_POSITION)
    mouse_at(app, monkeypatch, x, y, curses.BUTTON4_PRESSED)
    assert not app.test_calls


@pytest.mark.parametrize("expanded", [False, True])
def test_progress_bar_click_seeks_to_clicked_position(app, monkeypatch, expanded):
    app.fullscreen = expanded
    app.playback["item"]["duration_ms"] = 120000
    app.render()
    y, x, height, width, *_ = next(hit for hit in app.hits if hit[4] == "seek")
    mouse_at(app, monkeypatch, x + width - 1, y, curses.BUTTON1_CLICKED)
    settle(app)
    assert app.test_calls[-1] == ("control", ("seek", "120000"))


@pytest.mark.parametrize("mode", ["normal", "editing", "help", "layout_editor", "fullscreen"])
def test_ctrl_q_exits_from_every_input_mode(app, mode):
    if mode != "normal":
        setattr(app, mode, True)
    app.key("\x11")
    assert not app.running


def test_ctrl_q_exit_hint_is_visible_and_clickable_on_compact_terminal(app):
    app.s.size = (24, 80)
    app.render()
    assert any("Ctrl+Q" in text for _, _, text in app.s.calls)
    assert any(hit[4:] == ("key", "\x11") for hit in app.hits)


def test_checkpoint_records_selected_context_volume_and_elapsed_position(app, monkeypatch):
    saved = []
    monkeypatch.setattr(ui.API, "save_session", lambda *a, **kw: saved.append((a, kw)), raising=False)
    app.volume = 65
    app.playback = {
        "item": {"id": "playing", "duration_ms": 180000},
        "progress_ms": 42000,
        "is_playing": True,
    }
    app.updated = time.monotonic() - 2
    app.items = [("track", {"id": "selected", "_context_uri": "spotify:playlist:p"})]
    app.section = "Playlist"
    app.checkpoint()
    args, options = saved[0]
    assert 43900 <= args[0]["progress_ms"] <= 44500
    assert options["volume"] == 65
    assert options["view"]["selected_id"] == "selected"
    assert options["view"]["context_uri"] == "spotify:playlist:p"


def test_restore_selection_finds_identity_after_playlist_reordering(app):
    app.section = "Playlist"
    app.items = [("track", {"id": "new"}), ("track", {"id": "old"})]
    app.restore_selection = {"section": "Playlist", "selected": 0, "selected_id": "old"}
    app.restore_selected_row()
    assert app.selected == 1


def test_saved_open_playlist_and_volume_restore_into_a_new_interface(app, monkeypatch):
    from tspotify.api import Spotify

    memory = Spotify()
    second = None
    try:
        monkeypatch.setattr(ui.API, "save_session", memory.save_session, raising=False)
        app.volume = 65
        app.section = "Mix"
        app.history = [("Плейлисты", [], 0)]
        app.items = [("track", {"id": "t", "_context_uri": "spotify:playlist:p"})]
        app.playback = {"item": {"id": "t", "duration_ms": 180000}, "progress_ms": 42000, "is_playing": False}
        app.checkpoint()
        from tspotify import session

        data = session.load()
        monkeypatch.setattr(ui.API, "resume_data", data, raising=False)
        monkeypatch.setattr(ui.API, "current_volume", data["volume"], raising=False)
        monkeypatch.setattr(
            ui.API,
            "last_playback",
            {"item": data["track"], "progress_ms": data["position_ms"], "is_playing": False},
            raising=False,
        )
        second = ui.App(Window())
        settle(second)
        assert second.volume == 65 and second.section == "Mix"
        assert second.items[second.selected][1]["id"] == "t"
        assert second.playback["progress_ms"] == 42000 and not second.playback["is_playing"]
        assert not any(name == "start" for name, _ in app.test_calls)
    finally:
        memory.close()
        if second:
            second.pool.shutdown(wait=True, cancel_futures=True)
            second.art_pool.shutdown(wait=True, cancel_futures=True)
            second.cover_pool.shutdown(wait=True, cancel_futures=True)


def test_rapid_volume_keys_accumulate_and_stale_poll_cannot_reverse_direction(app, monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()
    levels = []

    def slow_control(command, value):
        levels.append(int(value))
        if len(levels) == 1:
            started.set()
            release.wait(2)
        return "volume confirmed"

    monkeypatch.setattr(ui.API, "control", slow_control)
    app.volume = 40
    try:
        app.key("+")
        app.drain()
        assert started.wait(1)
        app.events.put(("poll", {"device": {"volume_percent": 20}}, None))
        app.drain()
        assert app.volume == 45
        for _ in range(4):
            app.key("+")
        assert app.volume == 65
    finally:
        release.set()
    settle(app)
    assert levels == [45, 65] and app.volume == 65


def test_global_volume_events_use_the_same_queue_even_with_search_focused(app):
    app.volume = 40
    app.editing = True
    for _ in range(3):
        app.events.put(("hotkey", "volume-up", None))
    settle(app)
    assert app.volume == 55
    assert app.test_calls[-1] == ("control", ("volume", "55"))
    assert app.editing


def test_current_cover_does_not_wait_for_busy_thumbnail_workers(app, monkeypatch):
    import threading

    release = threading.Event()

    def blocked():
        release.wait(2)
        return []

    monkeypatch.setattr(ui, "cover", lambda *args: [[(1, 2, 3)]])
    try:
        for index in range(4):
            app.submit(f"thumb:blocked{index}", blocked)
        app.track_cover({"album": {"images": [{"url": "https://i.scdn.co/image/cover", "width": 300}]}})
        deadline = time.monotonic() + 1
        while not app.art and time.monotonic() < deadline:
            app.drain()
            time.sleep(0.005)
        assert app.art == [[(1, 2, 3)]]
        assert any(key.startswith("thumb:") for key in app.pending)
    finally:
        release.set()
    settle(app)


def test_cover_raster_is_cached_across_metadata_and_volume_redraws(app):
    image = [[(90, 150, 200)] * 32 for _ in range(32)]
    app.dot_image(image, 2, 2, 20, 10)
    entry = app.dot_cache[(id(image), 20, 10, False)]
    app.dot_image(image, 3, 3, 20, 10)
    assert app.dot_cache[(id(image), 20, 10, False)] is entry


@pytest.mark.parametrize(
    "key,command", [(curses.KEY_F7, "previous"), (curses.KEY_F8, "play-pause"), (curses.KEY_F9, "next")]
)
@pytest.mark.parametrize("mode", ["normal", "editing", "help", "layout_editor", "fullscreen"])
def test_media_function_keys_never_change_volume_and_work_in_every_mode(app, key, command, mode):
    app.volume = app.volume_applied = 40
    if mode != "normal":
        setattr(app, mode, True)
    app.key(key)
    settle(app)
    assert app.volume == 40
    assert app.test_calls[-1] == ("control", (command, None))


def test_volume_debounce_sends_one_final_value_for_a_burst(app, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ui, "volume_now", lambda: now[0])
    monkeypatch.setattr(ui, "VOLUME_DEBOUNCE", 0.18)
    monkeypatch.setattr(ui, "VOLUME_INTERVAL", 1.0)
    app.volume = app.volume_applied = 40
    for _ in range(8):
        app.key(curses.KEY_F12)
        app.drain()
        now[0] += 0.01
    assert not app.test_calls and app.volume == 80
    now[0] += 0.2
    settle(app)
    assert app.test_calls == [("control", ("volume", "80"))]
    for _ in range(100):
        app.key(curses.KEY_F12)
    now[0] += 1.1
    settle(app)
    assert app.test_calls[-1] == ("control", ("volume", "100"))
    calls = len(app.test_calls)
    for _ in range(100):
        app.key(curses.KEY_F12)
        app.drain()
    assert len(app.test_calls) == calls


def test_volume_429_keeps_latest_target_and_retries_only_after_retry_after(app, monkeypatch):
    from tspotify.api import RateLimited

    now = [100.0]
    monkeypatch.setattr(ui, "volume_now", lambda: now[0])
    monkeypatch.setattr(ui, "VOLUME_DEBOUNCE", 0.18)
    monkeypatch.setattr(ui, "VOLUME_INTERVAL", 1.0)
    calls = []

    def limited(command, value):
        calls.append(int(value))
        if len(calls) == 1:
            raise RateLimited(12)
        return "Громкость подтверждена"

    monkeypatch.setattr(ui.API, "control", limited)
    app.volume = app.volume_applied = 40
    app.key(curses.KEY_F12)
    now[0] += 0.2
    app.drain()
    deadline = time.monotonic() + 1
    while not app.volume_retry_until and time.monotonic() < deadline:
        app.drain()
        time.sleep(0.002)
    assert app.volume_retry_until > 112
    assert "в очереди" in app.notice and "Не удалось" not in app.notice
    for _ in range(6):
        app.key(curses.KEY_F12)
        app.drain()
    assert app.volume == 75 and calls == [45]
    now[0] = 111.9
    app.drain()
    assert calls == [45]
    app.events.put(("poll", {"device": {"volume_percent": 20}}, None))
    app.drain()
    assert app.volume == 75
    now[0] = 112.3
    settle(app)
    assert calls == [45, 75] and app.volume_applied == 75


def test_opposite_presses_cancel_before_any_http_request(app, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ui, "volume_now", lambda: now[0])
    monkeypatch.setattr(ui, "VOLUME_DEBOUNCE", 0.18)
    app.volume = app.volume_applied = 40
    app.key(curses.KEY_F12)
    app.key(curses.KEY_F11)
    now[0] += 1
    app.drain()
    assert app.volume == 40 and not app.test_calls


def test_unknown_duration_never_flashes_a_full_progress_bar(app):
    app.playback = {"item": {"id": "loading", "name": "Loading"}, "progress_ms": 50000, "is_playing": True}
    app.progress_area = (5, 4, 40)
    app.animate()
    bars = [text for y, x, text in app.s.calls if y == 5 and x == 4]
    assert not any("━" in text for text in bars)
    assert any("─" * 40 == text for text in bars)


def test_search_results_display_each_track_duration(app):
    app.items = [
        ("track", {"id": "a", "name": "Short", "duration_ms": 183000}),
        ("track", {"id": "b", "name": "Long", "duration": {"secs": 605}}),
    ]
    app.render_library(25, 140, 15)
    texts = [text for _, _, text in app.s.calls]
    assert "3:03" in texts
    assert "10:05" in texts


def test_local_volume_bypasses_network_backoff_and_is_saved_at_keypress(app, monkeypatch):
    saved = []
    monkeypatch.setattr(ui.API, "local_controls", True, raising=False)
    monkeypatch.setattr(ui.API, "rate_until", time.monotonic() + 60, raising=False)
    monkeypatch.setattr(ui.API, "save_session", lambda **kw: saved.append(kw), raising=False)
    app.volume = app.volume_applied = 70
    app.set_volume(75)
    assert saved[-1] == {"volume": 75}
    assert app.send_volume()
    settle(app)
    assert app.volume_applied == 75


def test_local_boot_zero_cannot_be_checkpointed_as_user_preference(app, monkeypatch):
    app.volume = app.volume_applied = 70
    monkeypatch.setattr(ui.API, "external", False, raising=False)
    app.events.put(("poll", {"device": {"volume_percent": 0}}, None))
    app.drain()
    assert app.volume == 70


def test_poll_does_not_move_playing_progress_backwards(app, monkeypatch):
    now = time.monotonic()
    app.updated = now - 2
    app.playback = {"item": {"id": "same"}, "progress_ms": 20000, "is_playing": True}
    app.events.put(("poll", {"item": {"id": "same"}, "progress_ms": 21300, "is_playing": True}, None))
    app.drain()
    assert app.playback["progress_ms"] >= 22000


def test_poll_started_before_transport_action_cannot_roll_back_progress(app):
    app.transport_revision = 4
    app.playback = {"item": {"id": "same"}, "progress_ms": 95000, "is_playing": True}
    app.events.put(
        ("poll", {"item": {"id": "same"}, "progress_ms": 10000, "is_playing": True, "_ui_revision": 3}, None)
    )
    app.drain()
    assert app.playback["progress_ms"] == 95000


def test_slow_track_start_does_not_block_local_volume(app, monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()

    def slow_start():
        started.set()
        release.wait(2)
        return ""

    monkeypatch.setattr(ui.API, "local_controls", True, raising=False)
    app.submit("command", slow_start)
    assert started.wait(0.5)
    try:
        app.set_volume(75)
        assert app.send_volume()
        deadline = time.monotonic() + 0.5
        while app.volume_applied != 75 and time.monotonic() < deadline:
            app.drain()
            time.sleep(0.001)
        assert app.volume_applied == 75
    finally:
        release.set()
        settle(app)
