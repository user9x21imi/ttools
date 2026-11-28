"""Curses interface. The same dotted renderer runs in Windows Terminal, macOS and Linux."""

import concurrent.futures
from collections import OrderedDict, deque
import curses
import json
import math
import queue
import sys
import threading
import time

from . import paths
from .api import RateLimited
from .art import cover, thumbnail, image_url, cached_cover
from .audio import Audio
from .editorial import CellGrid, char_width, dissolve_image, ease_out, fit_text, text_width, wrap_text
from .terminal import TerminalTitle

HOME = paths.HOME
CACHE = paths.BACKEND_CACHE
ART = paths.CACHE
CONFIG = paths.CONFIG / "layout.json"
SECTIONS = [
    "Плейлисты",
    "Любимые",
    "Альбомы",
    "Недавние",
    "Ваши миксы",
    "Новые релизы",
    "Рекомендации",
    "Миксы дня",
]
DEFAULT_ORDER = ["search", "player", "spectrum", "library"]
PANEL_NAMES = {
    "search": "Поиск",
    "player": "Текущий трек / обложка",
    "spectrum": "Аудиоспектр",
    "library": "Библиотека / результаты",
}
API = None
ASCII_ONLY = False
NO_SPLASH = False
NO_MOTION = False
LOW_POWER = False
VOLUME_FUNCTION_KEYS = {curses.KEY_F10: "m", curses.KEY_F11: "-", curses.KEY_F12: "+"}
TRANSPORT_FUNCTION_KEYS = {curses.KEY_F7: "previous", curses.KEY_F8: "play-pause", curses.KEY_F9: "next"}
VOLUME_DEBOUNCE = 0.18
VOLUME_INTERVAL = 1.0
volume_now = time.monotonic
DEMO_MODE = False


def cached(name, default):
    try:
        return json.loads((CACHE / (name + "_cache.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def artists(item):
    return ", ".join(a.get("name", "") for a in item.get("artists", []))


def duration(ms):
    s = max(0, int(ms / 1000))
    return f"{s // 60}:{s % 60:02d}"


def cli(*args):
    if args[:2] == ("get", "key") and args[2] == "playback":
        return API.playback()
    if args[0] == "search":
        return API.search(args[1])
    if args[0] == "playback":
        return API.control(args[1], args[2] if len(args) > 2 else None)
    raise ValueError("Неизвестная команда")


def open_context(kind, item_id, name):
    return API.context(kind, item_id, name)


def open_artist(item_id, name):
    return API.artist_profile(item_id, name)


class App:
    def __init__(self, screen):
        self.s = screen
        try:
            self.s.encoding = "utf-8"
        except (AttributeError, TypeError):
            pass
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.art_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.cover_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.transport_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.state_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.search_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        API.on_status = lambda message: self.events.put(("notice", message, None))
        API.on_volume_retry = lambda target, seconds, applied: self.events.put(
            ("volume_retry", (target, seconds, applied), None)
        )
        self.pending = set()
        self.transport_revision = 0
        self.thumbnails = OrderedDict()
        self.library_data = {}
        self.library_loaded_at = {}
        self.library_requested = set()
        self.playback = dict(getattr(API, "last_playback", {}))
        self.resume_view = dict(getattr(API, "resume_data", {}).get("view", {}))
        self.restore_selection = self.resume_view or None
        self.last_checkpoint = time.monotonic()
        self.updated = time.monotonic()
        self.prefetched_covers = set()
        self.transport_queue = deque(maxlen=32)
        self.queued_start = None
        self.art_url = ""
        self.art = []
        self.art_loading = False
        self.pending_art_from = None
        self.art_transition = None
        self.visual_track_id = (self.playback.get("item") or {}).get("id")
        self.dot_cache = OrderedDict()
        self.art_mode = "dots"
        self.art_mode_known = False
        self.native_supported = False
        self.native_last = None
        self.native_area = None
        self.smooth_bars = [0.0] * 32
        self.smooth_time = time.monotonic()
        self.query = ""
        self.search_due = 0.0
        self.search_cache = OrderedDict()
        self.search_query = ""
        self.search_category = "all"
        self.search_results = {"track": [], "artist": [], "album": [], "playlist": []}
        self.search_offsets = {"all": 0, "track": 0, "artist": 0, "album": 0, "playlist": 0}
        self.search_paging = {}
        self.search_scope = "spotify"
        self.global_query = ""
        self.context_query = ""
        self.context_items = None
        self.context_section = ""
        self.context_kind = "список"
        self.editing = False
        self.help = False
        self.share_dialog = None
        self.help_offset = 0
        self.layout_editor = False
        self.fullscreen = False
        self.motion_enabled = not NO_MOTION
        self.low_power = LOW_POWER
        self.panel_transition = None
        self.selection_transition = None
        self.volume_feedback_until = 0.0
        self._volume_feedback_visible = False
        self._render_grid = None
        self._display_grid = None
        self.focus_panel = "library"
        self.search_layout = False
        self.search_suspended = False
        self.hits = []
        self.layout_selected = 0
        self.order = DEFAULT_ORDER.copy()
        self.cover_right = False
        self.show_spectrum = True
        try:
            layout = json.loads(CONFIG.read_text(encoding="utf-8"))
            if sorted(layout.get("order", [])) == sorted(DEFAULT_ORDER):
                self.order = layout["order"]
            self.cover_right = bool(layout.get("cover_right", False))
            self.show_spectrum = bool(layout.get("show_spectrum", True))
            self.art_mode = layout.get("art_mode", "dots")
            self.art_mode_known = layout.get("art_mode") in ("dots", "ascii", "blocks")
            if self.art_mode not in ("dots", "ascii", "blocks"):
                self.art_mode = "dots"
        except (OSError, ValueError):
            pass
        if ASCII_ONLY:
            self.art_mode = "ascii"
            self.art_mode_known = True
        self.saved_tracks = cached("SavedTracks", {})
        self.favorite_changes = {}
        try:
            self.favorite_changes = json.loads((ART / "favorites.json").read_text(encoding="utf-8"))
            for uri, track in self.favorite_changes.items():
                if track is None:
                    self.saved_tracks.pop(uri, None)
                else:
                    self.saved_tracks[uri] = track
        except (OSError, ValueError):
            pass
        self.like_target = None
        self.section = "Плейлисты"
        self.items = []
        self.selected = 0
        self.notice = "Готово · / — поиск, ? — все клавиши"
        self.running = True
        self.volume = getattr(API, "current_volume", 0)
        self.volume_local_until = 0.0
        self.volume_applied = self.volume
        self.volume_dirty = False
        self.volume_due_at = 0.0
        self.volume_retry_until = 0.0
        self.volume_last_sent = float("-inf")
        self.muted_volume = getattr(API, "resume_data", {}).get("unmuted_volume", 35)
        self.audio = Audio(source=lambda: bool(API.backend and not getattr(API, "external", False)))
        self.colors = {}
        self.next_color = 20
        self.history = []
        self.artist_profile = None
        self.artist_group = "album"
        self.search_y = 2
        self.default_background = -1
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error:
            self.default_background = 0
        for i, fg, bg in [
            (1, 252, -1),
            (2, 78, -1),
            (3, 110, -1),
            (4, 244, -1),
            (5, 222, -1),
            (6, 255, 236),
            (7, 147, -1),
            (8, 210, -1),
            (9, 255, 235),
            (10, 110, 235),
            (11, 239, -1),
            (12, 78, 236),
        ]:
            self.init_pair(i, fg, bg)
        # Don't call bkgd() - it forces a background color even with use_default_colors()
        # and breaks terminal transparency on Windows PDCurses.
        # Let the terminal handle background (transparency, Acrylic, images, themes).
        self.s.timeout(16)
        self.s.keypad(True)
        curses.curs_set(0)
        root = self.resume_view.get("library", self.resume_view.get("section", "Плейлисты"))
        self.library(root if root in SECTIONS else "Плейлисты")
        self.query = self.resume_view.get("query", "")
        if not isinstance(self.query, str):
            self.query = ""
        context = self.resume_view.get("context_uri", "")
        if (
            isinstance(context, str)
            and context.startswith(("spotify:playlist:", "spotify:album:"))
            and len(context.split(":")) == 3
        ):
            _, kind, identity = context.split(":")
            self.submit("open", open_context, kind, identity, self.resume_view.get("section", "Треки"))
        elif self.query and str(self.resume_view.get("section", "")).startswith("Поиск:"):
            self.submit("search", cli, "search", self.query)
        else:
            self.restore_selected_row()
        self.fullscreen = bool(self.resume_view.get("fullscreen", False))
        self.track_cover(self.playback.get("item") or {})

    def restore_selected_row(self):
        view = self.restore_selection
        if not view or view.get("section") != self.section or not self.items:
            return
        index = view.get("selected", 0)
        if type(index) is not int:
            index = 0
        self.selected = next(
            (i for i, (_, item) in enumerate(self.items) if item.get("id") == view.get("selected_id")),
            max(0, min(index, len(self.items) - 1)),
        )
        self.restore_selection = None

    def push_history(self, section=None, items=None, selected=None):
        section = self.section if section is None else section
        items = self.items if items is None else items
        selected = self.selected if selected is None else selected
        view = {
            "artist_profile": self.artist_profile,
            "artist_group": self.artist_group,
            "query": self.query,
            "search_scope": self.search_scope,
            "context_items": self.context_items,
            "context_section": self.context_section,
            "context_kind": self.context_kind,
            "context_query": self.context_query,
            "search_layout": self.search_layout,
            "search_suspended": self.search_suspended,
            "search_query": self.search_query,
            "search_category": self.search_category,
            "search_results": {key: list(items) for key, items in self.search_results.items()},
            "search_offsets": dict(self.search_offsets),
            "search_paging": dict(self.search_paging),
        }
        self.history.append((section, list(items), selected, view))

    def artist_items(self, profile, group):
        releases = profile.get("releases", {})
        if group != "all":
            return [("album", item) for item in releases.get(group, [])]
        items = []
        seen = set()
        for name in ("album", "single", "appears_on", "compilation"):
            for item in releases.get(name, []):
                if item.get("id") not in seen:
                    seen.add(item.get("id"))
                    items.append(("album", item))
        items.sort(key=lambda pair: pair[1].get("release_date", ""), reverse=True)
        return items

    def select_artist_group(self, group):
        if group not in ("album", "single", "appears_on", "all") or not self.artist_profile:
            return
        selected_id = self.items[self.selected][1].get("id") if self.items else None
        self.artist_group = group
        self.items = self.artist_items(self.artist_profile, group)
        self.selected = next(
            (index for index, (_, item) in enumerate(self.items) if item.get("id") == selected_id), 0
        )

    def select_search_category(self, category):
        if category not in ("all", "track", "artist", "album", "playlist"):
            return
        self.search_category = category
        self.selected = 0
        self.update_search_items()

    def update_search_items(self):
        names = ("track", "artist", "album", "playlist")
        if self.search_category == "all":
            self.items = [
                (kind, item)
                for kind in names
                for item in self.search_results.get(kind, [])
            ]
        else:
            kind = self.search_category
            self.items = [(kind, item) for item in self.search_results.get(kind, [])]
        self.selected = max(0, min(self.selected, len(self.items) - 1)) if self.items else 0

    def load_more_search(self):
        if "search" in self.pending:
            self.notice = "Поиск ещё загружается…"
            return
        category = self.search_category
        available = any(
            self.search_paging.get(kind, {}).get("next")
            for kind in ("track", "artist", "album", "playlist")
        ) if category == "all" else self.search_paging.get(category, {}).get("next")
        if not available:
            self.notice = "Больше результатов нет"
            return
        self.search_offsets[category] = self.search_offsets.get(category, 0) + 10
        self.dispatch_search(category=category, offset=self.search_offsets[category])

    def go_back(self):
        if not self.history:
            return False
        self.begin_panel_transition()
        entry = self.history.pop()
        self.section, self.items, self.selected = entry[:3]
        view = entry[3] if len(entry) > 3 else None
        if view:
            for key in (
                "artist_profile", "artist_group", "query", "search_scope", "context_items",
                "context_section", "context_kind", "context_query", "search_layout",
                "search_suspended", "search_query", "search_category", "search_results",
                "search_offsets", "search_paging",
            ):
                if key in view:
                    setattr(self, key, view[key])
        else:
            self.artist_profile = None
            uri = (self.items[0][1].get("_context_uri") or "") if self.items else ""
            if uri and not self.section.startswith("Поиск:") and all(kind == "track" for kind, _ in self.items):
                self.context_items = list(self.items)
                self.context_section = self.section
                self.context_kind = uri.split(":")[1] if uri.count(":") >= 2 else "список"
                self.context_query = ""
                self.set_search_scope("context")
                self.query = ""
            else:
                self.context_items = None
                self.set_search_scope("spotify")
        return True

    def checkpoint(self):
        if DEMO_MODE or not hasattr(API, "save_session"):
            return
        item = self.items[self.selected][1] if self.items and 0 <= self.selected < len(self.items) else {}
        context = item.get("_context_uri", "")
        snapshot = dict(self.playback)
        progress = snapshot.get("progress_ms") or 0
        if snapshot.get("is_playing"):
            progress += max(0, time.monotonic() - self.updated) * 1000
        duration_ms = (snapshot.get("item") or {}).get("duration_ms")
        snapshot["progress_ms"] = int(min(progress, duration_ms) if duration_ms else progress)
        view = {
            "section": self.section,
            "library": self.history[0][0] if self.history else self.section,
            "context_uri": context,
            "selected": self.selected,
            "selected_id": item.get("id"),
            "query": self.query,
            "fullscreen": self.fullscreen,
        }
        try:
            API.save_session(snapshot, volume=self.volume, view=view)
        except (OSError, ValueError):
            self.notice = "Не удалось сохранить сессию: проверьте свободное место"
        self.last_checkpoint = time.monotonic()

    def init_pair(self, pair, fg, bg):
        if not curses.has_colors():
            return

        def adapt(index):
            if index < 0:
                return self.default_background
            if index < curses.COLORS:
                return index
            if index >= 232:
                return 7 if index > 245 else 0
            return {2: 2, 3: 6, 5: 3, 7: 5, 8: 1}.get(pair, 7)

        curses.init_pair(pair, adapt(fg), adapt(bg))

    def submit(self, key, fn, *args):
        if key in self.pending:
            return
        self.pending.add(key)
        if key in ("command", "transport"):
            self.transport_revision += 1
        revision = self.transport_revision

        def run():
            try:
                result = fn(*args)
                if key == "poll" and isinstance(result, dict):
                    result = {**result, "_ui_revision": revision}
                self.events.put((key, result, None))
            except RateLimited as exc:
                self.events.put((key, None, exc))
            except Exception as exc:
                self.events.put((key, None, str(exc)))

        pool = self.cover_pool if key.startswith("cover:") else self.art_pool if key.startswith("thumb:") else self.pool
        if key.startswith("prefetch:"):
            pool = self.art_pool
        if key == "poll":
            pool = self.state_pool
        if key == "search":
            pool = self.search_pool
        if key in ("volume", "command", "transport"):
            pool = self.transport_pool
        pool.submit(run)

    def library(self, section):
        self.set_search_scope("spotify")
        self.context_items = None
        if self.search_layout:
            self.leave_search_layout()
        self.fullscreen = False
        self.section = section
        self.selected = 0
        self.history = []
        if section in self.library_data:
            self.items = self.library_data[section]
            ttl = 60 if section == "Недавние" else 600
            if time.monotonic() - self.library_loaded_at.get(section, time.monotonic()) < ttl:
                return
            self.library_requested.discard(section)
        if section == "Плейлисты":
            self.items = [("playlist", x["Playlist"]) for x in cached("Playlists", []) if "Playlist" in x]
        elif section == "Любимые":
            self.items = [("track", x) for x in self.saved_tracks.values()]
        elif section == "Альбомы":
            self.items = [("album", x) for x in cached("SavedAlbums", [])]
        else:
            self.items = []
        if (not self.items or section != "Любимые") and section not in self.library_requested:
            if not self.items:
                self.notice = "Загружаю библиотеку…"
            self.library_requested.add(section)
            self.submit("library:" + section, API.library, section)

    def drain(self):
        changed = False
        while True:
            try:
                key, value, error = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            self.pending.discard(key)
            if key.startswith("prefetch:"):
                continue
            if key.startswith("cover:") and error:
                if key[6:] == self.art_url:
                    self.art_loading = False
                    self.pending_art_from = None
                continue
            if key == "hotkey":
                if value == "quit":
                    self.running = False
                    continue
                if value in ("volume-up", "volume-down", "mute"):
                    self.volume_key({"volume-up": "+", "volume-down": "-", "mute": "m"}[value])
                else:
                    self.command("playback", value)
                continue
            if key == "volume_retry":
                target, seconds, applied = value
                if not self.volume_dirty and "volume" not in self.pending:
                    self.volume = target
                self.volume_applied = applied
                self.volume_dirty = True
                self.volume_retry_until = volume_now() + seconds + 0.05
                self.volume_due_at = max(self.volume_due_at, self.volume_retry_until)
                self.volume_local_until = self.volume_due_at + 12
                self.volume_wait_notice()
                continue
            if isinstance(error, RateLimited):
                if key == "volume":
                    self.volume_dirty = True
                    self.volume_retry_until = volume_now() + error.seconds + 0.05
                    self.volume_due_at = max(self.volume_due_at, self.volume_retry_until)
                    self.volume_local_until = self.volume_due_at + 12
                    self.volume_wait_notice()
                elif not self.volume_dirty:
                    self.notice = f"Spotify занят · запросы возобновятся через {error.seconds} с"
                if key.startswith("library:"):
                    self.library_requested.discard(key[8:])
                continue
            if key == "volume":
                if error:
                    self.volume_dirty = False
                    self.notice = "Не удалось изменить громкость: " + error[:130]
                else:
                    requested, message = value
                    self.volume_applied = requested
                    self.volume_dirty = self.volume != requested
                    self.notice = (
                        message if not self.volume_dirty else f"Громкость {self.volume}% · применяется…"
                    )
                    self.volume_due_at = max(
                        self.volume_due_at,
                        self.volume_last_sent
                        + (0.025 if getattr(API, "local_controls", False) else VOLUME_INTERVAL),
                    )
                continue
            if key == "jam":
                if self.share_dialog and self.share_dialog[0] == "SPOTIFY JAM":
                    if error:
                        self.share_dialog = ("SPOTIFY JAM", "Не удалось создать Jam: " + str(error), "")
                    else:
                        names = ", ".join(
                            member.get("name", "Участник") for member in value.get("members", [])
                        )
                        body = (
                            "Участники: " + names + ". " if names else "Jam создан. "
                        ) + "Скопируйте приглашение кнопкой внизу и отправьте друзьям."
                        self.share_dialog = ("SPOTIFY JAM", body, value["url"])
                continue
            if key == "clipboard":
                self.notice = value
                if self.share_dialog:
                    title, _, url = self.share_dialog
                    self.share_dialog = (title, value, url)
                continue
            if key == "notice":
                self.notice = value
                continue
            if key.startswith("thumb:"):
                self.thumbnails[key[6:]] = value or []
                while len(self.thumbnails) > 128:
                    self.thumbnails.popitem(last=False)
                continue
            if error:
                if key == "search" and (self.search_scope == "context" or self.search_suspended):
                    continue
                if key == "transport":
                    self.transport_queue.clear()
                if key == "command" and self.queued_start:
                    item, self.queued_start = self.queued_start, None
                    self.start_track(item)
                    continue
                if key.startswith("library:"):
                    self.library_requested.discard(key[8:])
                if (
                    key == "poll"
                    and API.backend
                    and hasattr(API.backend, "alive")
                    and not API.backend.alive()
                    and ("Connection refused" in error or "timed out" in error)
                ):
                    self.notice = "Переподключаю фоновый плеер…"
                    self.submit("reconnect", API.backend.restart)
                    continue
                self.notice = "Ошибка: " + error[:180]
                continue
            if key == "reconnect":
                self.notice = "Плеер подключён"
                continue
            if key.startswith("library:"):
                section, items = value
                self.library_data[section] = items
                self.library_loaded_at[section] = time.monotonic()
                if section == "Любимые":
                    self.saved_tracks = {"spotify:track:" + item["id"]: item for _, item in items}
                    for uri, change in self.favorite_changes.items():
                        if change is None:
                            self.saved_tracks.pop(uri, None)
                        else:
                            self.saved_tracks[uri] = change
                    items = [("track", item) for item in self.saved_tracks.values()]
                    self.library_data[section] = items
                for kind, item in items:
                    thumb_key = kind + ":" + item["id"]
                    if item.get("images") and self.thumbnails.get(thumb_key) == []:
                        self.thumbnails.pop(thumb_key, None)
                if self.section == section:
                    previous = (
                        self.items[self.selected][1].get("id")
                        if self.items and self.selected < len(self.items)
                        else None
                    )
                    self.items = items
                    self.selected = next(
                        (i for i, (_, item) in enumerate(items) if item.get("id") == previous), 0
                    )
                    self.notice = (
                        "Сохраните нужные миксы в Spotify, чтобы они появились здесь"
                        if not items and section in ("Ваши миксы", "Миксы дня")
                        else f"Элементов: {len(items)}"
                    )
                self.restore_selected_row()
                continue
            if key == "poll":
                incoming = value or {}
                if incoming.get("_ui_revision", self.transport_revision) < self.transport_revision:
                    continue
                now = time.monotonic()
                old = self.playback
                if (
                    old.get("is_loading")
                    and "command" in self.pending
                    and (incoming.get("item") or {}).get("id") != (old.get("item") or {}).get("id")
                ):
                    continue
                same = (old.get("item") or {}).get("id") == (incoming.get("item") or {}).get("id")
                if (
                    same
                    and old.get("is_playing")
                    and incoming.get("is_playing")
                    and old.get("native_seek_revision") == incoming.get("native_seek_revision")
                ):
                    expected = (old.get("progress_ms") or 0) + max(0, now - self.updated) * 1000
                    actual = incoming.get("progress_ms") or 0
                    if abs(actual - expected) < 2500:
                        incoming = {**incoming, "progress_ms": expected}
                self.playback = incoming
                self.updated = now
                if not incoming.get("modes_pending") and self.notice.endswith(" · ожидает применения"):
                    self.notice = self.notice.removesuffix(" · ожидает применения")
                if incoming.get("is_playing") and self.notice.startswith(
                    ("Воспроизводится:", "Переподключаю", "Плеер подключён", "Команда выполнена")
                ):
                    self.notice = ""
                if (
                    (not getattr(API, "backend", None) or getattr(API, "external", False))
                    and not self.volume_dirty
                    and "volume" not in self.pending
                    and volume_now() >= self.volume_local_until
                ):
                    level = (self.playback.get("device") or {}).get("volume_percent")
                    if level is not None:
                        self.volume = level
                        self.volume_applied = level
                if time.monotonic() - self.last_checkpoint > 5:
                    self.checkpoint()
                self.track_cover(self.playback.get("item") or {})
            elif key.startswith("cover:"):
                url, image = value
                if url == self.art_url:
                    source = self.pending_art_from
                    self.pending_art_from = None
                    self.art_loading = False
                    self.set_art(image, animate=bool(source), source=source)
                elif self.art_url and self.art_loading:
                    self.submit("cover:" + self.art_url, lambda u=self.art_url: (u, cover(u, 256, 256)))
            elif key == "search":
                requested = (
                    value.get("_query", self.query.strip()) if isinstance(value, dict) else self.query.strip()
                )
                result = value.get("_results", value) if isinstance(value, dict) else value
                category = value.get("_category", "all") if isinstance(value, dict) else "all"
                offset = value.get("_offset", 0) if isinstance(value, dict) else 0
                selected_id = (
                    self.items[self.selected][1].get("id")
                    if self.section == "Поиск: " + requested and self.items and self.selected < len(self.items)
                    else None
                )
                if category == "all" and offset == 0:
                    self.search_cache[requested] = (time.monotonic(), result)
                    while len(self.search_cache) > 24:
                        self.search_cache.popitem(last=False)
                if self.search_suspended or self.search_scope == "context":
                    continue
                if requested != self.query.strip():
                    self.search_due = max(self.search_due, time.monotonic())
                    continue
                if self.search_query != requested:
                    previous_items = self.items if self.section == "Поиск: " + requested else []
                    self.search_query = requested
                    self.search_results = {"track": [], "artist": [], "album": [], "playlist": []}
                    self.search_offsets = {"all": 0, "track": 0, "artist": 0, "album": 0, "playlist": 0}
                    self.search_paging = {}
                    for kind, item in previous_items:
                        self.search_results.setdefault(kind, []).append(item)
                self.section = "Поиск: " + self.query
                plural = {"track": "tracks", "artist": "artists", "album": "albums", "playlist": "playlists"}
                paging = result.get("_paging", {}) if isinstance(result, dict) else {}
                for kind, key_name in plural.items():
                    values = (result or {}).get(key_name, [])
                    if not isinstance(values, list):
                        continue
                    existing = {item.get("id"): index for index, item in enumerate(self.search_results[kind])}
                    for item in values:
                        if not item:
                            continue
                        if item.get("id") in existing:
                            index = existing[item["id"]]
                            self.search_results[kind][index] = {
                                **self.search_results[kind][index],
                                **item,
                            }
                        else:
                            existing[item.get("id")] = len(self.search_results[kind])
                            self.search_results[kind].append(item)
                    if kind in paging:
                        self.search_paging[kind] = paging[kind]
                    for item in values:
                        if not item:
                            continue
                        thumb_key = kind + ":" + item.get("id", "")
                        if self.thumbnails.get(thumb_key) == [] and (
                            item.get("images") or (item.get("album") or {}).get("images")
                        ):
                            self.thumbnails.pop(thumb_key, None)
                self.update_search_items()
                if selected_id:
                    self.selected = next(
                        (i for i, (_, item) in enumerate(self.items) if item.get("id") == selected_id),
                        self.selected,
                    )
                self.restore_selected_row()
                if offset == 0:
                    self.search_offsets[category] = 0
                self.notice = f"Найдено: {len(self.items)} · Enter открыть · N ещё"
            elif key == "artist":
                profile = value or {}
                artist = profile.get("artist") or {}
                self.begin_panel_transition()
                previous_items = (
                    self.context_items
                    if self.search_scope == "context" and self.context_items is not None
                    else self.items
                )
                previous_id = self.items[self.selected][1].get("id") if self.items else None
                previous_selected = next(
                    (i for i, (_, item) in enumerate(previous_items) if item.get("id") == previous_id), 0
                )
                self.push_history(self.section, previous_items, previous_selected)
                self.artist_profile = profile
                self.artist_group = "album"
                if not profile.get("releases", {}).get("album"):
                    self.artist_group = "single"
                self.section = "ARTIST / " + artist.get("name", "Artist")
                self.items = self.artist_items(profile, self.artist_group)
                self.selected = 0
                self.context_items = None
                self.set_search_scope("spotify")
                self.query = ""
                self.search_suspended = True
                self.search_layout = False
                self.editing = False
                self.search_due = 0
                self.notice = f"Каталог: {sum(len(items) for items in profile.get('releases', {}).values())} релизов"
            elif key == "open":
                data = value or {}
                self.begin_panel_transition()
                if "Playlist" in data or "Album" in data:
                    data = data.get("Playlist", data.get("Album"))
                tracks = data.get("tracks", [])
                if isinstance(tracks, dict):
                    tracks = tracks.get("items", [])
                previous_items = (
                    self.context_items
                    if self.search_scope == "context" and self.context_items is not None
                    else self.items
                )
                previous_id = self.items[self.selected][1].get("id") if self.items else None
                previous_selected = next(
                    (i for i, (_, item) in enumerate(previous_items) if item.get("id") == previous_id), 0
                )
                self.push_history(self.section, previous_items, previous_selected)
                self.section = (data.get("playlist") or data.get("album") or data).get("name", "Треки")
                self.artist_profile = None
                for track in tracks:
                    if isinstance(track, dict):
                        target = track["track"] if isinstance(track.get("track"), dict) else track
                        target["_context_uri"] = data.get("context_uri")
                self.items = [
                    ("track", x["track"] if isinstance(x.get("track"), dict) else x)
                    for x in tracks
                    if isinstance(x, dict) and x.get("id", x.get("track"))
                ]
                self.context_items = list(self.items)
                self.context_section = self.section
                uri = data.get("context_uri") or ""
                self.context_kind = uri.split(":")[1] if uri.count(":") >= 2 else "список"
                self.context_query = ""
                self.set_search_scope("context")
                self.query = ""
                self.search_due = 0
                self.search_suspended = True
                self.selected = 0
                self.restore_selected_row()
                self.notice = f"Треков: {len(self.items)} · Enter слушать · ← назад"
            elif key in ("command", "transport"):
                self.transport_revision += 1
                if getattr(API, "local_controls", False) and getattr(API, "last_playback", None):
                    self.playback = dict(API.last_playback)
                    self.updated = time.monotonic()
                self.notice = (
                    value if isinstance(value, str) and not value.startswith("Воспроизводится:") else ""
                )
                self.track_cover((getattr(API, "last_playback", {}) or {}).get("item") or {})
                self.submit("poll", cli, "get", "key", "playback")
                if key == "transport" and self.transport_queue:
                    self.command(*self.transport_queue.popleft())
                if key == "command" and self.queued_start:
                    item, self.queued_start = self.queued_start, None
                    self.start_track(item)
            elif key == "favorite":
                track_id, was_liked, track = self.like_target
                if isinstance(value, bool):
                    was_liked = not value
                uri = "spotify:track:" + track_id
                if was_liked:
                    self.saved_tracks.pop(uri, None)
                else:
                    self.saved_tracks[uri] = track
                self.favorite_changes[uri] = None if was_liked else track
                (ART / "favorites.json").write_text(
                    json.dumps(self.favorite_changes, ensure_ascii=False), encoding="utf-8"
                )
                self.notice = "♡ Удалено из избранного" if was_liked else "♥ Добавлено в избранное"
                if self.section == "Любимые":
                    self.items = [("track", x) for x in self.saved_tracks.values()]
                    self.selected = max(0, min(self.selected, len(self.items) - 1))
                self.library_data.pop("Любимые", None)
        before = self.notice
        sent = self.send_volume()
        self.volume_wait_notice()
        return changed or sent or self.notice != before

    def put(self, y, x, text, color=1, bold=False, width=None):
        h, w = self.s.getmaxyx()
        offset = getattr(self, "_panel_x", 0)
        panel_w = getattr(self, "_panel_width", w)
        if width is None:
            width = max(0, panel_w - x - 1)
        else:
            width = min(width, max(0, panel_w - x - 1))
        x += offset
        if y < 0 or y >= h or x < 0 or x >= w or width <= 0:
            return
        text = str(text).replace("\n", " ").replace("\r", " ").replace("\t", " ")
        if ASCII_ONLY:
            text = text.translate(
                str.maketrans(
                    {
                        "╭": "+",
                        "╮": "+",
                        "╰": "+",
                        "╯": "+",
                        "─": "-",
                        "━": "=",
                        "│": "|",
                        "●": "*",
                        "›": ">",
                        "♥": "*",
                        "♡": "+",
                        "Ⅱ": "||",
                        "▶": ">",
                        "←": "<",
                        "↑": "^",
                        "↓": "v",
                        "⇄": "~",
                        "↻": "o",
                        "·": ".",
                        "…": "...",
                    }
                )
            )
        text = fit_text(text, width)
        if self._render_grid is not None:
            self._render_grid.write(y, x, text, color, bold)
        try:
            if not getattr(self, "_suppress_direct", False):
                self.s.addnstr(
                    y,
                    x,
                    text,
                    len(text),
                    (curses.color_pair(color) if curses.has_colors() else 0)
                    | (curses.A_BOLD if bold else 0),
                )
        except curses.error:
            pass

    def pixel_color(self, top, bottom):
        def quant(rgb):
            return 16 + 36 * round(rgb[0] / 255 * 5) + 6 * round(rgb[1] / 255 * 5) + round(rgb[2] / 255 * 5)

        key = quant(top), quant(bottom)
        if key not in self.colors and self.next_color < curses.COLOR_PAIRS:
            self.init_pair(self.next_color, *key)
            self.colors[key] = self.next_color
            self.next_color += 1
        return self.colors.get(key, 4)

    def symbol_image(self, image, y, x, width, height, *, ascii_only=False, cache=True):
        if not ascii_only:
            self.dot_image(image, y, x, width, height, cache=cache)
            return
        ramp = " .:-=+*#%@"
        for yy in range(height):
            row = image[min(len(image) - 1, yy * len(image) // height)]
            for xx in range(width):
                rgb = row[min(len(row) - 1, xx * len(row) // width)]
                self.put(y + yy, x + xx, ramp[min(9, int(sum(rgb) / 765 * 9))], 2)

    def dot_image(self, image, y, x, width, height, logo=False, cache=True):
        cache_key = (id(image), width, height, logo)
        cached_cells = self.dot_cache.get(cache_key) if cache else None
        if cached_cells:
            self.dot_cache.move_to_end(cache_key)
            for yy, xx, glyph, color in cached_cells[1]:
                self.put(y + yy, x + xx, glyph, color)
            return
        cells = []
        rows, cols = len(image), len(image[0])
        positions = [
            (0, 0, 1),
            (0, 1, 2),
            (0, 2, 4),
            (1, 0, 8),
            (1, 1, 16),
            (1, 2, 32),
            (0, 3, 64),
            (1, 3, 128),
        ]
        for yy in range(height):
            for xx in range(width):
                bits = 0
                colors = []
                for dx, dy, bit in positions:
                    pixel = image[min(rows - 1, (yy * 4 + dy) * rows // (height * 4))][
                        min(cols - 1, (xx * 2 + dx) * cols // (width * 2))
                    ]
                    lum = (0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]) / 255
                    bayer = ((0, 4), (6, 2), (1, 5), (7, 3))
                    threshold = 0.13 if logo else 0.08 + (bayer[dy][dx] + 0.5) / 8 * 0.88
                    if lum > threshold:
                        bits |= bit
                        colors.append(pixel)
                if colors:
                    rgb = tuple(
                        min(255, int(sum(c[k] for c in colors) / len(colors) * 1.3)) for k in range(3)
                    )
                    idx = (
                        16
                        + 36 * round(rgb[0] / 255 * 5)
                        + 6 * round(rgb[1] / 255 * 5)
                        + round(rgb[2] / 255 * 5)
                    )
                    key = ("dot", idx)
                    if key not in self.colors and self.next_color < curses.COLOR_PAIRS:
                        self.init_pair(self.next_color, idx, -1)
                        self.colors[key] = self.next_color
                        self.next_color += 1
                    color = self.colors.get(key, 3)
                    cells.append((yy, xx, chr(0x2800 + bits), color))
                    self.put(y + yy, x + xx, chr(0x2800 + bits), color)
                else:
                    cells.append((yy, xx, " ", 1))
                    self.put(y + yy, x + xx, " ")
        if cache:
            self.dot_cache[cache_key] = (image, cells)
            while len(self.dot_cache) > 8:
                self.dot_cache.popitem(last=False)

    def box(self, y, x, height, width, title="", active=False):
        if height < 3 or width < 4:
            return
        color = 3 if active else 11
        self.put(y, x, "╭" + "─" * (width - 2) + "╮", color)
        self.put(y + height - 1, x, "╰" + "─" * (width - 2) + "╯", color)
        for row in range(1, height - 1):
            self.put(y + row, x, "│", color)
            self.put(y + row, x + width - 1, "│", color)
        if title:
            self.put(y, x + 2, " " + title + " ", 3 if active else 4, width=width - 5)

    def hit(self, y, x, height, width, action, value):
        self.hits.append((y, x + getattr(self, "_panel_x", 0), height, width, action, value))

    def button(self, y, x, text, key):
        self.put(y, x, text, 3)
        self.hit(y, x, 1, text_width(text), "key", key)

    def button_row(self, y, w, actions, x=3):
        for text, key in actions:
            if x + text_width(text) > w - 2:
                break
            self.button(y, x, text, key)
            x += text_width(text) + 1

    def _draw_grid(self, grid, previous=None):
        for y, row in enumerate(grid.cells):
            x = 0
            while x < grid.width:
                cell = row[x]
                if previous is not None and cell == previous.cells[y][x]:
                    x += 1
                    continue
                if cell.glyph == "":
                    x += 1
                    continue
                style = cell.color, cell.bold
                start = x
                chars = []
                while x < grid.width:
                    current = row[x]
                    if previous is not None and current == previous.cells[y][x]:
                        break
                    if current.glyph == "":
                        x += 1
                        continue
                    if (current.color, current.bold) != style:
                        break
                    chars.append(current.glyph)
                    x += max(1, char_width(current.glyph))
                if not chars:
                    x = max(x, start + 1)
                    continue
                attributes = (
                    curses.color_pair(style[0]) if curses.has_colors() else 0
                ) | (curses.A_BOLD if style[1] else 0)
                try:
                    self.s.addnstr(y, start, "".join(chars), sum(len(glyph) for glyph in chars), attributes)
                except curses.error:
                    pass

    def _finish_render(self, now=None):
        now = time.monotonic() if now is None else now
        target = self._render_grid
        if target is None:
            return
        self._last_grid = target.clone()
        previous = self._display_grid
        transition = self.panel_transition
        if transition:
            source, started, duration_ms = transition
            if (source.height, source.width) != (target.height, target.width):
                self.panel_transition = None
            else:
                progress = ease_out((now - started) / duration_ms)
                if progress >= 1:
                    self.panel_transition = None
                else:
                    self._display_grid = source.compose(target, progress)
                    self._draw_grid(self._display_grid, previous)
                    self._suppress_direct = False
                    return
        if getattr(self, "_suppress_direct", False):
            self._draw_grid(target, previous)
        self._display_grid = target.clone()
        self._suppress_direct = False

    def begin_panel_transition(self, now=None):
        if not self.motion_enabled or self.low_power or self._display_grid is None:
            self.panel_transition = None
            return
        now = time.monotonic() if now is None else now
        self.panel_transition = (self._display_grid.clone(), now, 0.21)

    def visual_art(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.art_transition:
            return self.art
        source, started, duration_ms = self.art_transition
        progress = (now - started) / duration_ms
        if progress >= 1:
            self.art_transition = None
            return self.art
        return dissolve_image(source, self.art, ease_out(progress))

    def set_art(self, image, *, animate=True, source=None, now=None):
        now = time.monotonic() if now is None else now
        previous = source if source is not None else self.visual_art(now)
        self.art = image or []
        if previous and self.art and animate and self.motion_enabled and not self.low_power:
            self.art_transition = (previous, now, 0.28)
        else:
            self.art_transition = None

    def begin_selection(self, selected, now=None):
        now = time.monotonic() if now is None else now
        selected = max(0, min(len(self.items) - 1, selected)) if self.items else 0
        if selected == self.selected:
            return
        start = self.selection_position(now)
        self.selected = selected
        self.selection_transition = (start, float(selected), now, 0.1) if self.motion_enabled and not self.low_power else None

    def selection_position(self, now=None):
        if not self.selection_transition:
            return float(self.selected)
        now = time.monotonic() if now is None else now
        start, end, began, duration_ms = self.selection_transition
        progress = (now - began) / duration_ms
        if progress >= 1:
            self.selection_transition = None
            return float(self.selected)
        return start + (end - start) * ease_out(progress)

    def transport(self, y, w, x=3, rows=1):
        active = self.playback.get("is_playing", False)
        actions = [
            ("− VOL" if w >= 100 else "−", "-"),
            ("+ VOL" if w >= 100 else "+", "+"),
            ("‹ PREV" if w >= 100 else "‹", "p"),
            ("Ⅱ PAUSE" if active else "▶ PLAY" if w >= 100 else "Ⅱ" if active else "▶", " "),
            ("NEXT ›" if w >= 100 else "›", "n"),
            ("MUTE" if w >= 100 else "M", "m"),
            ("♡ SAVE" if w >= 100 else "♡", "f"),
            ("SHARE" if w >= 100 else "SH", "y"),
            ("JAM" if w >= 100 else "J", "j"),
        ]
        column, row = x, 0
        for text, key in actions:
            if column + text_width(text) > w - 2:
                row += 1
                column = x
            if row >= rows:
                break
            self.button(y + row, column, text, key)
            column += text_width(text) + 1

    def mode_buttons(self, y, w, x=3):
        mode = self.playback.get("repeat_state", "off")
        repeat = {"off": "OFF", "context": "ALL", "track": "ONE"}.get(mode, "OFF")
        shuffle = "ON" if self.playback.get("shuffle_state") else "OFF"
        if w >= 100:
            self.button(y, x, f"S · SHUFFLE {shuffle}", "s")
            offset = text_width(f"S · SHUFFLE {shuffle}") + 3
            self.button(y, x + offset, f"R · REPEAT {repeat}", "r")
        else:
            self.button(y, x, f"S {shuffle}", "s")
            self.button(y, x + 7, f"R {repeat}", "r")

    def mouse(self):
        self.mouse_changed = False
        try:
            _, x, y, _, state = curses.getmouse()
        except curses.error:
            return
        wheel_up = state & getattr(curses, "BUTTON4_PRESSED", 0)
        wheel_down = state & getattr(curses, "BUTTON5_PRESSED", 0)
        clicked = state & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_DOUBLE_CLICKED)
        self.mouse_changed = bool(clicked or wheel_up or wheel_down)
        if clicked:
            previous = getattr(self, "last_mouse_click", None)
            now = time.monotonic()
            if (
                state & curses.BUTTON1_DOUBLE_CLICKED
                and previous
                and previous[:2] == (x, y)
                and now - previous[2] < 0.5
            ):
                return  # A single click already opened/played this row.
            self.last_mouse_click = (x, y, now)
        if self.help and (wheel_up or wheel_down):
            self.help_offset = max(0, self.help_offset + (-3 if wheel_up else 3))
            return
        # Panel focus also applies when the pointer hits a child control (seek, art).
        if self.search_layout:
            for py, px, ph, pw, action, panel in self.hits:
                if (
                    action == "panel"
                    and panel in ("player", "spectrum")
                    and py <= y < py + ph
                    and px <= x < px + pw
                ):
                    self.leave_search_layout(panel)
                    self.mouse_changed = True
                    break
        for by, bx, height, width, action, value in reversed(self.hits):
            if not (by <= y < by + height and bx <= x < bx + width):
                continue
            if action in ("row", "panel"):
                panel = "library" if action == "row" else value
                self.mouse_changed |= self.focus_panel != panel
                self.focus_panel = panel
                if clicked and panel == "search":
                    self.enter_search_layout()
                elif panel in ("player", "spectrum") and self.search_layout:
                    self.leave_search_layout(panel)
                if wheel_up or wheel_down:
                    if self.focus_panel == "library":
                        self.begin_selection(self.selected + (-3 if wheel_up else 3))
                    return
            if not clicked:
                continue
            if action == "row":
                self.editing = False
                self.begin_selection(value)
                self.key("\n")
            elif action == "panel":
                self.editing = value == "search"
            elif action == "key":
                if value not in ("\n", "\r", curses.KEY_ENTER):
                    self.editing = False
                self.key(value)
            elif action == "layout_row":
                self.layout_selected = value
            elif action == "seek":
                duration_ms = (self.playback.get("item") or {}).get("duration_ms") or 0
                if duration_ms and "command" not in self.pending:
                    position = round((x - bx) * duration_ms / max(1, width - 1))
                    self.command("playback", "seek", str(position))
            elif action == "volume":
                self.set_volume(round((x - bx) * 100 / max(1, width - 1)))
            return

    def render_fullscreen(self, h, w):
        self.progress_area = self.spectrum_area = None
        self.put(0, 2, "● TSPOTIFY · PLAYER MODE", 2, True)
        self.button(0, max(2, w - 12), "F3 EXIT", curses.KEY_F3)
        compact = h < 30
        side_by_side = w >= 100
        if compact:
            art_h = max(5, min(8, h - 16, (w - 26) // 2))
        elif side_by_side:
            art_h = max(8, min(h - 21, (w - 48) // 4, 28))
        else:
            art_h = max(7, min(h - 27, (w - 40) // 4, 18))
        art_w = art_h * 2
        if side_by_side:
            ay = max(3, (h - art_h - 13) // 2)
            ax = w - art_w - 4 if self.cover_right else 4
        else:
            ay = 3 if compact else max(3, (h - art_h - 15) // 2)
            ax = max(3, (w - art_w) // 2)
        art = self.visual_art()
        if art:
            self.symbol_image(
                art,
                ay,
                ax,
                art_w,
                art_h,
                ascii_only=ASCII_ONLY or self.art_mode == "ascii",
                cache=not bool(self.art_transition),
            )
        else:
            self.put(ay + art_h // 2, ax, "♪  NO COVER", 4, width=art_w)
        item = self.playback.get("item") or {}
        active = self.playback.get("is_playing", False)
        content_w = w - art_w - 13 if side_by_side else w - 8
        if self.cover_right and side_by_side:
            x = 4
            content_w = max(12, ax - x - 5)
        elif side_by_side:
            x = ax + art_w + 5
            content_w = max(12, w - x - 4)
        else:
            x = 4
        title_y = (
            max(3, ay + (art_h - 12) // 2)
            if side_by_side
            else ay + art_h + 1
        )
        self.put(title_y, x, "NOW PLAYING", 4, width=content_w)
        title_lines = wrap_text(item.get("name", "Выберите трек в библиотеке"), content_w, 2 if not compact else 1)
        for line, text in enumerate(title_lines):
            self.put(title_y + 1 + line, x, text, 1, True, width=content_w)
        info_y = title_y + 3
        self.put(info_y, x, artists(item) or "Spotify", 2, width=content_w)
        if (item.get("artists") or [{}])[0].get("id"):
            self.hit(info_y, x, 1, content_w, "key", "g")
        self.put(info_y + 1, x, (item.get("album") or {}).get("name", ""), 4, width=content_w)
        status = (
            "◌ LOADING"
            if self.playback.get("is_loading")
            else "● PLAYING"
            if active
            else "QUEUE ENDED · Space from start"
            if self.playback.get("queue_ended")
            else "Ⅱ PAUSED · Space to play"
        )
        self.put(info_y + 2, x, status, 2 if active else 4, width=content_w)
        if self.art_loading and not compact:
            self.put(info_y + 3, x, "COVER · LOADING", 12, width=content_w)
        total = item.get("duration_ms") or 0
        ms = min(
            total,
            (self.playback.get("progress_ms") or 0)
            + ((time.monotonic() - self.updated) * 1000 if active else 0),
        )
        progress_y = (
            min(h - 6, ay + art_h + 1)
            if side_by_side
            else min(h - 6, info_y + 4)
        )
        progress_x = 4
        progress_w = w - 8
        bar_w = max(8, progress_w - 18)
        self.progress_area = (progress_y, progress_x, bar_w)
        self.hit(progress_y, progress_x, 1, bar_w, "seek", None)
        filled = int(bar_w * ms / total) if total else 0
        self.put(progress_y, progress_x, "━" * filled, 2)
        self.put(progress_y, progress_x + filled, "─" * (bar_w - filled), 11)
        self.put(progress_y, progress_x + bar_w + 2, f"{duration(ms)} / {duration(total)}", 4, width=16)
        self.render_next(progress_y - 1, progress_x, progress_w)
        sy = min(h - 5, progress_y + 2)
        self.put(sy - 1, 4, "AUDIO / LIVE · " + self.audio.status, 4, width=w - 8)
        self.spectrum_area = (sy, 4, max(1, h - sy - 5), w - 8)
        self.spectrum(*self.spectrum_area)

    def render_next(self, y, x, width):
        item = self.playback.get("next_item") or {}
        if item.get("name"):
            label = "Далее: " + artists(item) + " — " + item["name"]
            if self.playback.get("queue_ended"):
                label = "С начала: " + artists(item) + " — " + item["name"]
        else:
            label = (
                "Далее: очередь завершена"
                if self.playback.get("queue_ended")
                else "Далее: загружаю название…"
                if self.playback.get("next_track_id")
                else "Далее: нет следующего трека в очереди"
            )
        self.put(y, x, label, 3, width=width)

    def render_header(self, h, w):
        self.put(0, 2, "● TSPOTIFY", 2, True)
        if not self.fullscreen:
            actions = [("F3 PLAYER", curses.KEY_F3), ("/ SEARCH", "/"), ("? HELP", "?")]
            if w >= 130:
                actions.insert(1, ("L LAYOUT", "L"))
            total = sum(text_width(label) for label, _ in actions) + len(actions) - 1
            x = max(15, w - total - 3)
            for label, key in actions:
                self.button(0, x, label, key)
                x += text_width(label) + 1
        if h > 1:
            item = self.playback.get("item") or {}
            title = item.get("name") or "MUSIC / LESS NOISE"
            prefix = "DEMO / NO AUDIO · " if DEMO_MODE else "NOW · " if self.playback.get("is_playing") else "READY · "
            self.put(1, 3, prefix + title, 5 if DEMO_MODE else 4, width=w - 6)

    def render_footer(self, h, w):
        y = h - 4
        now = time.monotonic()
        pulsing = now < self.volume_feedback_until and self.motion_enabled
        self._volume_feedback_visible = pulsing
        color = 2 if pulsing else 4
        self.put(y, 3, "VOL", color, bold=pulsing)
        bar_x = 8
        bar_w = min(20, max(8, w // 5))
        self.hit(y, bar_x, 1, bar_w, "volume", None)
        filled = round(self.volume * bar_w / 100)
        self.put(y, bar_x, "━" * filled + "─" * (bar_w - filled), color)
        self.put(y, bar_x + bar_w + 2, f"{self.volume:3d}%", color, bold=pulsing)
        if pulsing:
            self.put(y, bar_x + bar_w + 9, "VOLUME", 2, True)

        self.transport(h - 3, w, x=3, rows=1)
        self.mode_buttons(h - 2, w, x=3)
        notice_x = max(38, w // 2)
        self.put(h - 2, notice_x, self.notice, 4, width=w - notice_x - 2)
        self.button_row(
            h - 1,
            w,
            [
                ("ENTER PLAY", "\n"),
                ("/ SEARCH", "/"),
                ("BACK", curses.KEY_LEFT),
                ("P PLAYLIST", "P"),
                ("? HELP", "?"),
                ("Ctrl+Q", "\x11"),
            ],
            x=3,
        )

    def render(self):
        self.hits = []
        self._panel_x = 0
        self._panel_width = self.s.getmaxyx()[1]
        self.spectrum_area = self.progress_area = None
        h, w = self.s.getmaxyx()
        self._suppress_direct = bool(
            self.panel_transition
            and self._display_grid
            and (self._display_grid.height, self._display_grid.width) == (h, w)
        )
        if not self._suppress_direct:
            self.s.erase()
        self._render_grid = CellGrid(h, w)
        if h < 24 or w < 78:
            self.spectrum_area = None
            self.progress_area = None
            self.put(1, 2, "RESIZE · MINIMUM 78 × 24", 5, True)
            self.put(3, 2, "q / Ctrl+Q  quit", 4)
            self._finish_render()
            self.s.refresh()
            return
        self.render_header(h, w)
        if self.fullscreen:
            self.render_fullscreen(h, w)
            self.render_footer(h, w)
            if self.help:
                self.render_help(h, w)
            if self.share_dialog:
                self.render_share(h, w)
            curses.curs_set(0)
            self._finish_render()
            self.s.refresh()
            return

        if self.artist_profile and not self.search_layout:
            footer_y = h - 4
            self.render_artist_profile(2, w, max(1, footer_y - 2))
            self.render_footer(h, w)
            if self.help:
                self.render_help(h, w)
            if self.share_dialog:
                self.render_share(h, w)
            curses.curs_set(0)
            self._finish_render()
            self.s.refresh()
            return

        footer_y = h - 4
        body_y = 2
        body_h = max(1, footer_y - body_y)
        wide = h >= 30 and w >= 110 and w >= 2 * h and not self.search_layout
        if self.search_layout:
            self.render_search(2, w, 3)
            content_y = 6
            content_h = max(4, footer_y - content_y - 1)
            if wide:
                library_w = max(44, int(w * 0.58))
                self._panel_x, self._panel_width = 0, library_w
                self.render_library(content_y, library_w, content_h)
                self._panel_x, self._panel_width = library_w + 1, w - library_w - 1
                player_h = max(6, content_h - (5 if self.show_spectrum else 1))
                self.render_player(content_y, self._panel_width, player_h)
                if self.show_spectrum:
                    self.render_spectrum(content_y + player_h + 1, self._panel_width, content_h - player_h - 1)
                self._panel_x, self._panel_width = 0, w
            else:
                player_h = 2 if self.show_spectrum else 3
                spectrum_h = 3 if self.show_spectrum else 0
                library_h = max(3, content_h - player_h - spectrum_h - (2 if spectrum_h else 1))
                self.render_library(content_y, w, library_h)
                player_y = content_y + library_h + 1
                self.render_player(player_y, w, player_h)
                if spectrum_h:
                    self.render_spectrum(player_y + player_h + 1, w, spectrum_h)
        elif wide:
            library_w = max(43, int(w * 0.38))
            music_w = w - library_w - 1
            spectrum_h = min(8, max(5, body_h // 4)) if self.show_spectrum else 0
            player_h = body_h - spectrum_h - (1 if spectrum_h else 0)
            self._panel_x, self._panel_width = 0, music_w
            left_order = [name for name in self.order if name in ("player", "spectrum")]
            y = body_y
            for name in left_order:
                if name == "spectrum" and not self.show_spectrum:
                    continue
                height = player_h if name == "player" else spectrum_h
                getattr(self, "render_" + name)(y, music_w, height)
                y += height + 1
            self._panel_x, self._panel_width = music_w + 1, library_w
            self.render_library(body_y, library_w, body_h)
            self._panel_x, self._panel_width = 0, w
        else:
            spectrum_h = min(4 if h >= 30 else 3, max(1, body_h - 7)) if self.show_spectrum else 0
            player_h = min(max(7, round(body_h * 0.43)), body_h - spectrum_h - 3)
            library_h = max(2, body_h - player_h - spectrum_h - (2 if spectrum_h else 1))
            heights = {"player": player_h, "spectrum": spectrum_h, "library": library_h}
            y = body_y
            for name in (panel for panel in self.order if panel in heights):
                height = heights[name]
                if height <= 0 or (name == "spectrum" and not self.show_spectrum):
                    continue
                getattr(self, "render_" + name)(y, w, height)
                y += height + 1

        self.render_footer(h, w)
        if self.help:
            self.render_help(h, w)
        if self.layout_editor:
            self.render_layout(h, w)
        if self.share_dialog:
            self.render_share(h, w)
        if self.editing and not self.help and not self.layout_editor and not self.share_dialog:
            curses.curs_set(1)
            self.s.move(self.search_y, min(w - 4, 5 + text_width(self.query)))
        else:
            curses.curs_set(0)
        self._finish_render()
        self.s.refresh()

    def render_search(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "search")
        context = self.search_scope == "context" and self.context_items is not None
        label = "SEARCH / THIS LIST" if context else "SEARCH / SPOTIFY"
        self.put(y, 3, label, 2 if self.editing else 4, bold=self.editing, width=w - 6)
        if height <= 1:
            return
        self.search_y = y + 1
        hint = "Type a track, artist, album or playlist" if not context else "Search in this playlist"
        self.put(y + 1, 3, "⌕  " + (self.query or hint), 1 if self.editing else 4, width=w - 6)
        if height > 2:
            labels = [
                ("all", "ALL 0"),
                ("track", "TRACKS 1"),
                ("artist", "ARTISTS 2"),
                ("album", "ALBUMS 3"),
                ("playlist", "PLAYLISTS 4"),
            ]
            x = 3
            for category, label in labels:
                self.put(y + 2, x, label, 2 if self.search_category == category else 4, self.search_category == category)
                self.hit(y + 2, x, 1, text_width(label), "key", "search-category:" + category)
                x += text_width(label) + 2
            has_more = (
                any(self.search_paging.get(kind, {}).get("next") for kind in ("track", "artist", "album", "playlist"))
                if self.search_category == "all"
                else bool(self.search_paging.get(self.search_category, {}).get("next"))
            )
            more_label = "N MORE" if has_more else "END"
            more_x = min(w - text_width(more_label) - 2, x + 1)
            self.put(y + 2, more_x, more_label, 3 if has_more else 4, width=max(1, w - more_x - 2))
            if has_more:
                self.hit(y + 2, more_x, 1, text_width(more_label), "key", "n")
        if context:
            self.button(y, w - 14, "F2 ALL", curses.KEY_F2)

    def render_artist_profile(self, y, w, height):
        profile = self.artist_profile or {}
        artist = profile.get("artist") or {}
        name = artist.get("name", "Artist")
        self.hit(y, 1, height, w - 2, "panel", "artist")
        self.put(y, 3, "ARTIST / PROFILE", 2, True)
        if w >= 70:
            self.button(y, w - 25, "y LINK", "y")
            self.button(y, w - 13, "BACK", curses.KEY_LEFT)
        image_w = min(18, max(10, w // 7))
        image_h = min(8, max(4, image_w // 2))
        image_y = y + 1
        image_x = 3
        key = "artist:" + str(artist.get("id", ""))
        image = self.thumbnails.get(key)
        if image:
            self.dot_image(image, image_y, image_x, image_w, image_h)
        else:
            self.put(image_y, image_x, "·" * image_w, 3)
            if key not in self.thumbnails and sum(p.startswith("thumb:") for p in self.pending) < 4:
                self.submit("thumb:" + key, self.load_thumbnail, "artist", artist)
        text_x = image_x + image_w + 3
        text_w = max(8, w - text_x - 5)
        self.put(image_y, text_x, name, 1, True, width=text_w)
        genres = artist.get("genres") or []
        metadata = " · ".join(genres[:3]) if genres else "SPOTIFY CATALOG"
        self.put(image_y + 1, text_x, metadata, 4, width=text_w)
        details = []
        if isinstance(artist.get("followers"), dict) and artist["followers"].get("total") is not None:
            details.append(f"{artist['followers']['total']:,} followers")
        if artist.get("popularity") is not None:
            details.append(f"popularity {artist['popularity']}")
        if details:
            self.put(image_y + 2, text_x, " · ".join(details), 4, width=text_w)
        else:
            self.put(image_y + 2, text_x, "Доступные метаданные Spotify", 4, width=text_w)
        self.put(image_y + 3, text_x, "Топ треков недоступен · показан каталог релизов", 3, width=text_w)

        tabs_y = image_y + image_h + 1
        tabs = [
            ("album", "1 ALBUMS"),
            ("single", "2 SINGLES + EP"),
            ("appears_on", "3 APPEARS ON"),
            ("all", "4 ALL RELEASES"),
        ]
        tx = 3
        for group, label in tabs:
            if tx + text_width(label) >= w - 2:
                break
            selected = self.artist_group == group
            self.put(tabs_y, tx, label, 2 if selected else 4, selected)
            self.hit(tabs_y, tx, 1, text_width(label), "key", "artist-group:" + group)
            tx += text_width(label) + 2
        count = len(self.items)
        partial = ""
        if self.artist_group == "all" and profile.get("unavailable_groups"):
            partial = " · недоступно: " + ", ".join(profile["unavailable_groups"])
        self.put(
            tabs_y + 1,
            3,
            f"{profile.get('catalog_label', 'Доступный каталог')} · {count} релизов{partial}",
            4,
            width=w - 6,
        )
        list_y = tabs_y + 2
        rows = max(1, (y + height - list_y) // 2)
        start = max(0, min(self.selected - rows + 1, len(self.items) - rows))
        self.list_area = (list_y, rows)
        for row, (_, release) in enumerate(self.items[start : start + rows]):
            index = start + row
            yy = list_y + row * 2
            selected = index == self.selected
            self.hit(yy, 3, 2, w - 6, "row", index)
            if selected:
                self.put(yy, 3, " " * max(1, w - 6), 6)
                self.put(yy + 1, 3, " " * max(1, w - 6), 6)
            art_key = "album:" + str(release.get("id", ""))
            art = self.thumbnails.get(art_key)
            if art:
                self.dot_image(art, yy, 5, 4, 2)
            elif art_key not in self.thumbnails and sum(p.startswith("thumb:") for p in self.pending) < 4:
                self.submit("thumb:" + art_key, self.load_thumbnail, "album", release)
            label_w = max(8, w - 21)
            self.put(yy, 11, release.get("name", "Untitled release"), 1 if not selected else 6, selected, width=label_w)
            group = release.get("_artist_group") or release.get("album_group") or release.get("album_type", "release")
            group_label = {"album": "ALBUM", "single": "SINGLE / EP", "appears_on": "APPEARS ON", "compilation": "COMPILATION"}.get(group, "RELEASE")
            year = (release.get("release_date") or "")[:4]
            tracks = release.get("total_tracks")
            tail = " · ".join(part for part in (group_label, year, f"{tracks} tracks" if tracks is not None else "") if part)
            self.put(yy + 1, 11, tail, 4, width=label_w)
            self.put(yy, 3, "›" if selected else " ", 2, True)
        if not self.items:
            unavailable = profile.get("unavailable_groups", {})
            if self.artist_group == "all" and unavailable:
                message = "CATALOG PARTIAL · Spotify не предоставил группы " + ", ".join(unavailable)
            elif self.artist_group in unavailable:
                message = f"Группа недоступна для этого входа Spotify (HTTP {unavailable[self.artist_group]})"
            else:
                message = "В каталоге пока нет релизов"
            self.put(list_y, 4, message, 4, width=w - 8)

    def render_player(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "player")
        if height <= 0:
            return
        mode = {"dots": "DOTS", "ascii": "ASCII", "blocks": "BLOCKS"}.get(self.art_mode, "DOTS")
        self.put(y, 3, "NOW PLAYING", 2 if self.focus_panel == "player" else 4, bold=True)
        self.put(y, 18, mode, 4, width=max(1, w - 24))
        if w >= 70:
            self.button(y, w - 12, "F3 VIEW", curses.KEY_F3)
        if height < 4:
            item = self.playback.get("item") or {}
            self.put(y, 3, "NOW  " + item.get("name", "Choose a track"), 1, True, width=w - 6)
            return
        art_h = max(3, min(height - 2, (w - 40) // 2))
        art_h = min(art_h, max(3, (w - 12) // 2))
        art_w = art_h * 2
        art_y = y + 1
        art_x = w - art_w - 3 if self.cover_right else 3
        text_x = 3 if self.cover_right else art_x + art_w + 4
        text_w = max(10, w - text_x - (art_w + 6 if self.cover_right else 3))
        if self.cover_right:
            text_w = max(10, art_x - text_x - 3)
        else:
            text_w = max(10, w - text_x - 3)
        self.native_area = (art_y, art_x, art_w, art_h)
        self.hit(art_y, art_x, art_h, art_w, "key", curses.KEY_F3)
        art = self.visual_art()
        if art:
            self.symbol_image(
                art,
                art_y,
                art_x,
                art_w,
                art_h,
                ascii_only=ASCII_ONLY or self.art_mode == "ascii",
                cache=not bool(self.art_transition),
            )
        else:
            self.put(art_y + art_h // 2, art_x, "♪", 2, width=art_w)
        item = self.playback.get("item") or {}
        active = self.playback.get("is_playing", False)
        liked = "spotify:track:" + str(item.get("id")) in self.saved_tracks
        self.hit(art_y, text_x, 1, text_w, "key", " ")
        title_lines = wrap_text(item.get("name", "Choose something from the library"), text_w, 2)
        title_y = art_y
        for line, text in enumerate(title_lines):
            self.put(title_y + line, text_x, text, 1, True, width=text_w)
        detail_y = title_y + max(1, len(title_lines))
        self.put(detail_y, text_x, artists(item) or "Spotify", 2, width=text_w)
        if (item.get("artists") or [{}])[0].get("id"):
            self.hit(detail_y, text_x, 1, text_w, "key", "g")
        if height >= 6:
            self.put(detail_y + 1, text_x, (item.get("album") or {}).get("name", ""), 4, width=text_w)
        status_y = min(art_y + art_h - 1, detail_y + 2)
        status = (
            "◌ LOADING"
            if self.playback.get("is_loading")
            else "● PLAYING"
            if active
            else "QUEUE ENDED"
            if self.playback.get("queue_ended")
            else "Ⅱ PAUSED"
        )
        self.put(status_y, text_x, status, 2 if active else 4, width=text_w)
        if self.art_loading:
            self.put(status_y + 1, text_x, "COVER · LOADING", 12, width=text_w)
        if liked:
            self.put(y, max(text_x, w - 24), "♥ SAVED", 2, width=min(18, text_w))
        progress = (self.playback.get("progress_ms") or 0) + (
            (time.monotonic() - self.updated) * 1000 if active else 0
        )
        total = item.get("duration_ms") or 0
        progress = min(progress, total)
        if height >= 5:
            progress_y = y + height - 1
            bar_w = max(4, min(text_w - 2, 22))
            self.progress_area = (progress_y, text_x, bar_w)
            self.hit(progress_y, text_x, 1, bar_w, "seek", None)
            filled = int(bar_w * progress / total) if total else 0
            self.put(progress_y, text_x, "━" * filled + "─" * (bar_w - filled), 2)
            self.put(progress_y, text_x + bar_w + 2, f"{duration(progress)} / {duration(total)}", 4, width=max(1, text_w - bar_w - 2))
        else:
            self.progress_area = None

    def render_spectrum(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "spectrum")
        if height <= 0:
            return
        self.put(y, 3, "AUDIO / LIVE", 2 if self.focus_panel == "spectrum" else 4, bold=True)
        self.put(y, 17, self.audio.status, 4, width=w - 20)
        bars_h = max(1, height - 1)
        self.spectrum(y + 1, 3, bars_h, w - 6)
        self.spectrum_area = (y + 1, 3, bars_h, w - 6)

    def animate(self):
        if self.help or self.layout_editor or self.share_dialog:
            return
        now = time.monotonic()
        if (
            self.panel_transition
            or self.art_transition
            or self.selection_transition
            or now < self.volume_feedback_until
            or self._volume_feedback_visible
        ):
            self.render()
            return
        if (self.show_spectrum or self.fullscreen) and getattr(self, "spectrum_area", None):
            self.spectrum(*self.spectrum_area)
        if getattr(self, "progress_area", None):
            y, x, width = self.progress_area
            item = self.playback.get("item") or {}
            total = item.get("duration_ms") or 0
            ms = self.playback.get("progress_ms") or 0
            if self.playback.get("is_playing"):
                ms += (time.monotonic() - self.updated) * 1000
            ms = min(ms, total)
            filled = int(width * ms / total) if total else 0
            self.put(y, x, "━" * filled, 2)
            self.put(y, x + filled, "─" * (width - filled), 11)
            self.put(y, x + width + 2, f"{duration(ms)} / {duration(total)}", 4)
        if self.editing and self.search_y < self.s.getmaxyx()[0]:
            self.s.move(self.search_y, min(self.s.getmaxyx()[1] - 4, 5 + text_width(self.query)))
        if self._render_grid is not None:
            self._display_grid = self._render_grid.clone()
        self.s.refresh()

    def render_library(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "library")
        if height <= 0:
            return
        section_title = self.query if self.section.startswith("Поиск:") and self.query else self.section
        self.put(y, 3, "LIBRARY", 2 if self.focus_panel == "library" else 4, bold=True)
        self.put(y, 13, section_title, 1, True, width=w - 16)
        if height < 4:
            if self.items:
                _, item = self.items[max(0, min(self.selected, len(self.items) - 1))]
                self.put(y + 1, 3, "› " + item.get("name", ""), 1, True, width=w - 6)
            return

        list_y = y + 1
        if not self.search_layout:
            labels = ["PL", "LIKED", "ALBUMS", "RECENT", "MIXES", "NEW", "FOR YOU", "DAILY"]
            tabs_y = y + 1
            tx = 3
            for index, (section, label) in enumerate(zip(SECTIONS, labels), 1):
                text = f"{index} {label}"
                size = text_width(text)
                if tx + size > w - 3:
                    tabs_y += 1
                    tx = 3
                if tabs_y >= y + height - 2:
                    break
                selected_tab = self.section == section
                self.put(tabs_y, tx, text, 2 if selected_tab else 4, bold=selected_tab)
                self.hit(tabs_y, tx, 1, size, "key", str(index))
                tx += size + 2
            list_y = tabs_y + 1

        detailed = self.search_layout or self.section.startswith("Поиск:")
        with_art = bool(self.items and (detailed or self.items[0][0] in ("playlist", "album")))
        row_h = 3 if detailed and height >= 10 else 2 if with_art and height >= 8 else 1
        rows = max(1, (y + height - list_y) // row_h)
        start = max(0, min(self.selected - rows + 1, len(self.items) - rows))
        self.list_area = (list_y, rows)
        visual_index = self.selection_position()
        for row, (kind, data) in enumerate(self.items[start : start + rows]):
            identity = start + row
            selected = identity == self.selected
            yy = list_y + row * row_h
            self.hit(yy, 3, row_h, w - 6, "row", identity)
            transition = self.selection_transition
            shade = 6 if selected else 1
            if transition and not self.low_power:
                old_index, _, began, duration_ms = transition
                progress = ease_out((time.monotonic() - began) / duration_ms)
                if identity == int(round(old_index)) and not selected:
                    shade = 10 if progress < 0.55 else 4
                elif selected and progress < 0.55:
                    shade = 10
            if selected:
                self.put(yy, 3, " " * max(0, w - 6), shade)
                if row_h >= 2:
                    self.put(yy + 1, 3, " " * max(0, w - 6), shade)

            name_x = 5
            if with_art and row_h >= 2:
                key = kind + ":" + data.get("id", "")
                image = self.thumbnails.get(key)
                if image:
                    self.thumbnails.move_to_end(key)
                    if ASCII_ONLY:
                        self.put(yy, 5, "[ART]", 3)
                    else:
                        self.dot_image(image, yy, 5, 5, 2)
                else:
                    self.put(yy, 5, "·····", 11)
                    thumb_jobs = sum(pending.startswith("thumb:") for pending in self.pending)
                    if key not in self.thumbnails and thumb_jobs < 4:
                        self.submit("thumb:" + key, self.load_thumbnail, kind, data)
                name_x = 12

            owner = data.get("owner") or [""]
            by = artists(data) or (
                owner[0]
                if isinstance(owner, list)
                else owner.get("display_name", "")
                if isinstance(owner, dict)
                else ""
            )
            if kind == "artist":
                genres = data.get("genres") or []
                identity = data.get("id", "")
                discriminator = ", ".join(genres[:2]) or "Spotify artist"
                if identity:
                    discriminator += " · ID " + identity[:6]
                by = discriminator
            duration_label = ""
            if kind == "track":
                milliseconds = data.get("duration_ms") or 0
                if not milliseconds and isinstance(data.get("duration"), dict):
                    milliseconds = data["duration"].get("secs", 0) * 1000
                duration_label = duration(milliseconds) if milliseconds else "--:--"
            duration_w = text_width(duration_label)
            name_w = max(4, w - name_x - duration_w - 8)
            self.put(yy, name_x, data.get("name", ""), shade, selected, width=name_w)
            if duration_label:
                self.put(yy, w - duration_w - 4, duration_label, 4 if not selected else 6)
            if row_h >= 2:
                self.put(yy + 1, name_x, by, 3, width=w - name_x - 6)
                if row_h >= 3:
                    album_name = (data.get("album") or {}).get("name", "")
                    self.put(yy + 2, name_x, album_name, 4, width=w - name_x - 6)
            elif w >= 70:
                self.put(yy, name_x + name_w + 1, by, 4, width=max(1, w - name_x - name_w - duration_w - 9))

        marker_y = list_y + round((visual_index - start) * row_h)
        if list_y <= marker_y < y + height:
            self.put(marker_y, 3, "›", 2, True)
        if not self.items:
            if self.section.startswith("Поиск:"):
                empty = "TYPE TO SEARCH" if not self.query.strip() else "SEARCHING…" if "search" in self.pending else "NO RESULTS"
            else:
                empty = "EMPTY · / search · 1–8 library sections"
            self.put(list_y, 4, empty, 4, width=w - 8)

    def load_thumbnail(self, kind, item):
        images = item.get("images") or (item.get("album") or {}).get("images") or []
        if images:
            ready = cached_cover(image_url(images, 256))
            if ready:
                return [
                    [ready[y * len(ready) // 24][x * len(ready[0]) // 24] for x in range(24)]
                    for y in range(24)
                ]
            return cover(image_url(images, 24), 24, 24)
        return thumbnail(kind, item["id"])

    def render_layout(self, h, w):
        self.hits = []
        bw = min(w - 4, 78)
        bx, by = (w - bw) // 2, max(0, (h - 19) // 2)
        for yy in range(19):
            self.put(by + yy, bx, " " * bw, 9)
        self.put(by + 1, bx + 2, "РАСКЛАДКА · порядок окон сверху вниз", 2, True)
        for i, name in enumerate(self.order):
            selected = i == self.layout_selected
            self.hit(by + 3 + i, bx + 2, 1, bw - 4, "layout_row", i)
            self.put(
                by + 3 + i,
                bx + 2,
                (" › " if selected else "   ") + PANEL_NAMES[name],
                6 if selected else 9,
                selected,
                width=bw - 4,
            )
        for i, line in enumerate(
            [
                "↑/↓ выбрать окно · K/J переместить выше/ниже",
                "Shift+↑ / Shift+↓ — тоже переместить окно",
                "c — обложка " + ("справа" if self.cover_right else "слева"),
                "v — спектр " + ("показан" if self.show_spectrum else "скрыт"),
                "d — вернуть стандартную раскладку",
                "Enter / s — сохранить и закрыть",
                "Esc — закрыть (без сохранения на диск)",
            ]
        ):
            self.put(by + 9 + i, bx + 2, line, 10, width=bw - 4)

        self.button_row(
            by + 16,
            bx + bw,
            [("[K Выше]", "K"), ("[J Ниже]", "J"), ("[c Обложка]", "c"), ("[v Спектр]", "v")],
            x=bx + 2,
        )
        self.button_row(
            by + 17,
            bx + bw,
            [("[Enter Сохранить]", "\n"), ("[d Сброс]", "d"), ("[Esc Закрыть]", "\x1b")],
            x=bx + 2,
        )

    def save_layout(self):
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "order": self.order,
                    "cover_right": self.cover_right,
                    "show_spectrum": self.show_spectrum,
                    "art_mode": self.art_mode,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        tmp.replace(CONFIG)
        self.notice = "Раскладка сохранена · L — настроить окна"

    def finish_intro(self, now):
        self.intro_active = False
        self.intro_skip_requested = False
        self.skip_input_until = now + 0.12
        try:
            curses.flushinp()
            curses.mouseinterval(180)
        except curses.error:
            pass
        self.s.erase()

    def route_control(self, action):
        if self.intro_active:
            self.intro_skip_requested = True
        elif time.monotonic() >= self.skip_input_until:
            self.events.put(("hotkey", action, None))

    def intro_key(self, key):
        if key == curses.KEY_RESIZE:
            return False
        if key == curses.KEY_MOUSE:
            try:
                state = curses.getmouse()[4]
            except curses.error:
                return False
            return bool(
                state
                & (
                    curses.BUTTON1_PRESSED
                    | curses.BUTTON1_CLICKED
                    | curses.BUTTON1_DOUBLE_CLICKED
                    | getattr(curses, "BUTTON2_PRESSED", 0)
                    | getattr(curses, "BUTTON3_PRESSED", 0)
                )
            )
        return True

    def spectrum(self, y, x, height, width):
        now = time.monotonic()
        dt = min(0.12, now - self.smooth_time)
        self.smooth_time = now
        target = self.audio.bars
        for i in range(32):
            value = 0.2 * target[max(0, i - 1)] + 0.6 * target[i] + 0.2 * target[min(31, i + 1)]
            tau = 0.14 if value > self.smooth_bars[i] else 0.52
            self.smooth_bars[i] += (value - self.smooth_bars[i]) * (1 - math.exp(-dt / tau))
        count = min(32, max(1, width // 2))
        stride = max(2, width // count)
        x += max(0, (width - count * stride) // 2)
        glyphs = " ▁▂▃▄▅▆▇█"
        levels = [self.smooth_bars[i * 32 // count] * height for i in range(count)]
        for j in range(height):
            pieces = []
            for level in levels:
                amount = max(0, min(8, int((level - (height - j - 1)) * 8)))
                if self.fullscreen and not ASCII_ONLY:
                    dots = round(amount / 2)
                    mask = sum((0xC0, 0x24, 0x12, 0x09)[:dots])
                    ch = chr(0x2800 + mask) if mask else " "
                else:
                    ch = glyphs[amount]
                pieces.append(ch * (stride - 1) + " ")
            color = 7 if j < height * 0.25 else (3 if j < height * 0.6 else 2)
            self.put(y + j, x, "".join(pieces), color)

    def render_share(self, h, w):
        self.hits = []
        import textwrap

        title, body, url = self.share_dialog
        bw = min(w - 4, 92)
        lines = textwrap.wrap(body, bw - 6)
        if url:
            lines += [""] + textwrap.wrap(url, bw - 6)
        by, bx = max(1, (h - len(lines) - 7) // 2), (w - bw) // 2
        for row in range(len(lines) + 7):
            self.put(by + row, bx, " " * bw, 9)
        self.put(by + 1, bx + 3, title, 2, True, width=bw - 6)
        for row, line in enumerate(lines):
            self.put(by + row + 3, bx + 3, line, 9, width=bw - 6)
        actions = [("[Esc Закрыть]", "\x1b")]
        if url:
            actions.insert(0, ("[c Копировать]", "c"))
        self.button_row(by + len(lines) + 4, bx + bw, actions, x=bx + 3)

    def share(self, selected=False):
        from .sharing import share_url

        if selected and self.items:
            kind, item = self.items[self.selected]
            item = {**item, "type": kind}
        elif self.artist_profile:
            item = {**(self.artist_profile.get("artist") or {}), "type": "artist"}
        else:
            item = self.playback.get("item") or {}
        url = share_url(item)
        if not url:
            self.notice = "Сначала выберите трек, альбом или плейлист"
            return
        self.share_dialog = ("ПОДЕЛИТЬСЯ", item.get("name", "Spotify"), url)
        self.copy_share()

    def copy_share(self):
        from .sharing import copy_link

        if self.share_dialog and self.share_dialog[2]:
            self.submit("clipboard", copy_link, self.share_dialog[2])

    def render_help(self, h, w):
        self.hits = []
        lines = [
            ("/ или строка поиска", "В альбоме/плейлисте — поиск внутри списка"),
            ("F2", "Общий поиск Spotify"),
            ("0–4 в поиске", "Все · треки · артисты · альбомы · плейлисты"),
            ("N в поиске", "Следующая страница результатов"),
            ("Ввод в поиске", "Треки · артисты · альбомы · плейлисты"),
            ("↓ / Tab в поиске", "Перейти к результатам"),
            ("Enter в поиске", "Открыть артиста / альбом / плейлист или трек"),
            ("Enter в списке", "Открыть артиста / альбом / плейлист или трек"),
            ("P", "Включить весь плейлист / альбом"),
            ("g", "Страница артиста текущего трека"),
            ("y / Y", "Ссылка Spotify на артиста / выбранный элемент"),
            ("1–4 в профиле", "Альбомы · синглы/EP · участия · все релизы"),
            ("Tab", "Переключить поиск и список"),
            ("↑ / ↓ · PgUp / PgDn", "Выбрать строку / страницу"),
            ("Space", "Пауза / продолжить"),
            ("n / p", "Следующий / предыдущий трек"),
            ("+ / −", "Громкость ±5%"),
            ("F7 / F8 / F9", "Назад / играть-пауза / далее"),
            ("F10 / F11 / F12", "Без звука / тише / громче"),
            ("m", "Выключить / вернуть звук"),
            ("f", "Текущий трек: добавить / убрать ♥"),
            ("1–3 · 4–8", "Библиотека · недавние, миксы, новинки"),
            ("F3 · кнопка Плеер", "Крупная обложка и точечный спектр"),
            ("Щелчок мышью", "Открыть плейлист / включить трек"),
            ("o", "Открыть список треков плейлиста / альбома"),
            ("← / Backspace", "Вернуться к предыдущему списку"),
            ("s / r", "Перемешивание / повтор: список → трек → выкл."),
            ("y / Y", "Ссылка: текущий трек / выбранная строка"),
            ("j", "Создать Jam / получить приглашение"),
            ("L", "Редактор порядка окон и обложки"),
            ("a", "Обложка: точки / ASCII / блоки"),
            ("? / F1 · Esc", "Показать / закрыть эту справку"),
            ("Ctrl+Q · q · Ctrl+C", "Сохранить сессию и выйти"),
        ]
        visible = max(1, h - 5)
        self.help_offset = max(0, min(self.help_offset, len(lines) - visible))
        lines = lines[self.help_offset : self.help_offset + visible]
        bw = min(w - 4, 86)
        bx, by = (w - bw) // 2, max(0, (h - len(lines) - 5) // 2)
        for yy in range(len(lines) + 5):
            self.put(by + yy, bx, " " * bw, 9)
        self.put(by + 1, bx + 2, "КЛАВИШИ · ↑/↓ прокрутка", 2, True)
        self.button(by + 1, bx + bw - 16, "[Esc Закрыть]", "\x1b")
        for i, (key, desc) in enumerate(lines):
            self.put(by + 3 + i, bx + 2, key, 10, True, width=25)
            self.put(by + 3 + i, bx + 29, desc, 9, width=bw - 31)

        self.button_row(
            by + len(lines) + 3,
            bx + bw,
            [("[↑ Выше]", curses.KEY_UP), ("[↓ Ниже]", curses.KEY_DOWN)],
            x=bx + 2,
        )

    def command(self, *args):
        if "transport" in self.pending:
            self.transport_queue.append(args)
            return
        if not getattr(API, "local_controls", False):
            self.notice = "Выполняю…"
        self.submit("transport", cli, *args)

    def start_track(self, item):
        item = dict(item)
        queue_items = (
            self.context_items
            if self.search_scope == "context" and self.context_items is not None
            else self.items
        )
        tracks = [track for kind, track in queue_items if kind == "track" and len(track.get("id", "")) == 22]
        index = next((i for i, track in enumerate(tracks) if track.get("id") == item.get("id")), None)
        if index is not None:
            first = max(0, index - 20) if len(tracks) > 100 else 0
            item["_queue_uris"] = ["spotify:track:" + track["id"] for track in tracks[first : first + 100]]
        self.notice = "Загружается: " + item.get("name", "трек")
        self.playback = {
            **self.playback,
            "item": item,
            "progress_ms": 0,
            "is_playing": False,
            "is_loading": True,
        }
        self.updated = time.monotonic()
        self.track_cover(item)
        if "command" in self.pending:
            self.queued_start = item
            if hasattr(API, "cancel_start"):
                API.cancel_start()
            return
        self.submit("command", API.start, item)

    def track_cover(self, item):
        identity = item.get("id")
        changed_track = bool(self.visual_track_id and identity and identity != self.visual_track_id)
        if identity:
            self.visual_track_id = identity
        images = (item.get("album") or {}).get("images") or item.get("images") or []
        url = image_url(images, 256)
        if url != self.art_url:
            previous = self.visual_art()
            self.art_url = url
            if not url:
                self.art_loading = False
                self.pending_art_from = None
                self.set_art([], animate=False)
                return
            ready = cached_cover(url)
            if ready:
                self.art_loading = False
                self.pending_art_from = None
                self.set_art(ready, animate=changed_track)
            else:
                self.pending_art_from = previous
                self.art_loading = True
                if not self.art:
                    self.set_art([], animate=False)
                self.submit("cover:" + url, lambda u=url: (u, cover(u, 256, 256)))

    def prefetch_nearby(self):
        # Load a bounded window while the user browses, before Enter/Next.
        nearby = self.items[max(0, self.selected - 1) : self.selected + 5]
        if self.search_scope == "context" and self.context_items and self.items:
            identity = self.items[self.selected][1].get("id")
            index = next(
                (i for i, (_, item) in enumerate(self.context_items) if item.get("id") == identity), None
            )
            if index is not None:
                nearby += self.context_items[index + 1 : index + 4]
        for kind, item in nearby:
            if kind != "track":
                continue
            if hasattr(API, "remember_tracks"):
                API.remember_tracks(item)
            images = (item.get("album") or {}).get("images") or item.get("images") or []
            url = image_url(images, 256)
            if (
                url
                and url not in self.prefetched_covers
                and sum(k.startswith("prefetch:") for k in self.pending) < 2
            ):
                self.prefetched_covers.add(url)
                if len(self.prefetched_covers) > 128:
                    self.prefetched_covers = {url}
                self.submit("prefetch:" + url, cover, url, 256, 256)

    def set_search_scope(self, scope):
        if scope == self.search_scope:
            return
        if self.search_scope == "context":
            self.context_query = self.query
        else:
            self.global_query = self.query
        self.search_scope = scope
        self.query = self.context_query if scope == "context" else self.global_query

    def filter_context(self):
        if self.context_items is None:
            return
        words = self.query.casefold().split()
        selected_id = (
            self.items[self.selected][1].get("id") if self.items and self.selected < len(self.items) else None
        )
        self.items = []
        for kind, item in self.context_items:
            text = " ".join(
                (
                    item.get("name", ""),
                    artists(item),
                    (
                        (item.get("album") or {}).get("name")
                        or (self.context_section if self.context_kind == "album" else "")
                    ),
                )
            ).casefold()
            if all(word in text for word in words):
                self.items.append((kind, item))
        self.selected = next(
            (i for i, (_, item) in enumerate(self.items) if item.get("id") == selected_id), 0
        )
        self.context_query = self.query
        self.section = self.context_section
        self.search_due = 0
        self.search_suspended = True
        self.notice = (
            f"В списке: {len(self.items)} / {len(self.context_items)} · Esc очистить · F2 весь Spotify"
        )

    def enter_search_layout(self, scope=None):
        already = self.search_layout
        previous_scope = self.search_scope
        local = self.context_items is not None and (
            self.section == self.context_section or self.search_scope == "context"
        )
        self.set_search_scope(scope or ("context" if local else "spotify"))
        self.search_layout = True
        self.search_suspended = False
        self.fullscreen = False
        self.editing = True
        self.focus_panel = "search"
        if self.search_scope == "context":
            self.filter_context()
        elif self.query.strip() and (not already or previous_scope != self.search_scope):
            self.schedule_search()

    def leave_search_layout(self, panel="player"):
        self.search_layout = False
        self.search_suspended = True
        self.search_due = 0
        self.editing = False
        self.focus_panel = panel

    def schedule_search(self):
        if self.search_scope == "context":
            self.filter_context()
            return
        self.search_layout = True
        self.search_suspended = False
        query = self.query.strip()
        if query != self.search_query:
            self.search_query = query
            self.search_category = "all"
            self.search_results = {"track": [], "artist": [], "album": [], "playlist": []}
            self.search_offsets = {"all": 0, "track": 0, "artist": 0, "album": 0, "playlist": 0}
            self.search_paging = {}
        self.section = "Поиск: " + query
        candidates = dict(self.saved_tracks)
        for entries in self.library_data.values():
            for kind, item in entries:
                if kind == "track" and item.get("id"):
                    candidates[item["id"]] = item
        words = query.casefold().split()
        matches = []
        seen = set()
        if words:
            for item in candidates.values():
                text = " ".join(
                    (item.get("name", ""), artists(item), (item.get("album") or {}).get("name", ""))
                ).casefold()
                if item.get("id") not in seen and all(word in text for word in words):
                    matches.append(("track", item))
                    seen.add(item.get("id"))
                    if len(matches) >= 10:
                        break
        self.items = matches
        self.selected = 0
        self.notice = (
            "Из библиотеки · ищу в Spotify…"
            if matches
            else "Подсказки по мере ввода · ↓ результаты · Enter поиск"
        )
        cached = self.search_cache.get(query)
        if cached and time.monotonic() - cached[0] < 30:
            self.events.put(("search", {"_query": query, "_results": cached[1], "_category": "all", "_offset": 0}, None))
            self.search_due = 0
        else:
            self.search_due = time.monotonic() + 0.18 if query else 0

    def dispatch_search(self, category=None, offset=None):
        if self.search_scope == "context":
            self.filter_context()
            return
        query = self.query.strip()
        if not query:
            self.search_due = 0
            return
        if "search" in self.pending:
            return
        category = category or self.search_category
        offset = self.search_offsets.get(category, 0) if offset is None else offset
        self.search_due = 0
        self.notice = "Ищу в Spotify…"
        self.submit(
            "search",
            lambda q, c=category, o=offset: {
                "_query": q,
                "_category": c,
                "_offset": o,
                "_results": API.search(q, c, o),
            },
            query,
        )

    def update_live_search(self):
        if self.search_suspended:
            return
        if self.search_due and time.monotonic() >= self.search_due:
            self.dispatch_search()

    def volume_wait_notice(self):
        if self.volume_dirty and volume_now() < self.volume_retry_until:
            seconds = max(1, math.ceil(self.volume_retry_until - volume_now()))
            self.notice = f"Громкость {self.volume}% в очереди · подтверждено {self.volume_applied}% · автоматически через {seconds} с"

    def send_volume(self):
        if not self.volume_dirty or "volume" in self.pending:
            return False
        now = volume_now()
        remaining = (
            0
            if getattr(API, "local_controls", False)
            else max(0.0, getattr(API, "rate_until", 0.0) - time.monotonic())
        )
        if remaining:
            self.volume_retry_until = max(self.volume_retry_until, now + remaining + 0.05)
            self.volume_due_at = max(self.volume_due_at, self.volume_retry_until)
            self.volume_local_until = self.volume_due_at + 12
        if now < self.volume_due_at or now < self.volume_last_sent + (
            0.025 if getattr(API, "local_controls", False) else VOLUME_INTERVAL
        ):
            return False
        target = self.volume
        self.volume_last_sent = now
        self.volume_dirty = False
        self.submit("volume", lambda: (target, API.control("volume", str(target))))
        return True

    def set_volume(self, value):
        target = max(0, min(100, int(value)))
        if target == self.volume:
            return  # Holding a key at 0/100 must never flood Spotify.
        self.volume = target
        self.volume_feedback_until = time.monotonic() + 0.45
        self.volume_dirty = "volume" in self.pending or self.volume != self.volume_applied
        self.volume_due_at = max(
            volume_now() + (0 if getattr(API, "local_controls", False) else VOLUME_DEBOUNCE),
            self.volume_last_sent + (0.025 if getattr(API, "local_controls", False) else VOLUME_INTERVAL),
            self.volume_retry_until,
        )
        self.volume_local_until = self.volume_due_at + 12
        if not DEMO_MODE and hasattr(API, "save_session"):
            API.save_session(volume=target)
        self.notice = (
            f"Громкость {self.volume}% · применяется…" if self.volume_dirty else f"Громкость: {self.volume}%"
        )

    def volume_key(self, k):
        if k == "m":
            self.muted_volume = self.volume or getattr(self, "muted_volume", 35)
            volume = 0 if self.volume else self.muted_volume
        else:
            volume = self.volume + (5 if k in ("+", "=") else -5)
        self.set_volume(volume)

    def key(self, k):
        if k in ("\x03", "\x11"):
            self.running = False
            return
        if k == curses.KEY_MOUSE:
            self.mouse()
            return
        if k != curses.KEY_RESIZE and k not in VOLUME_FUNCTION_KEYS and k not in TRANSPORT_FUNCTION_KEYS:
            if getattr(self, "share_dialog", None):
                if k in ("\x1b", "q", "\n", "\r"):
                    self.share_dialog = None
                elif k == "c":
                    self.copy_share()
                return
        if k == curses.KEY_F3:
            self.begin_panel_transition()
            self.leave_search_layout()
            self.fullscreen = not self.fullscreen
            self.editing = self.help = self.layout_editor = False
            return
        if k == "\x1b" and self.fullscreen:
            self.begin_panel_transition()
            self.fullscreen = False
            return
        if k == "\x1b" and self.artist_profile and not self.search_layout and self.go_back():
            return
        if k == curses.KEY_RESIZE:
            self.s.clear()
            return
        if k == curses.KEY_F2:
            if self.search_scope == "context" and self.context_items is not None:
                identity = self.items[self.selected][1].get("id") if self.items else None
                index = next(
                    (i for i, (_, item) in enumerate(self.context_items) if item.get("id") == identity), 0
                )
                self.push_history(self.context_section, self.context_items, index)
            self.help = False
            self.enter_search_layout("spotify")
            if not self.query.strip():
                self.section = "Поиск: "
                self.items = []
                self.selected = 0
            return
        if k in VOLUME_FUNCTION_KEYS:
            self.volume_key(VOLUME_FUNCTION_KEYS[k])
            return
        if k in TRANSPORT_FUNCTION_KEYS:
            self.command("playback", TRANSPORT_FUNCTION_KEYS[k])
            return
        if self.layout_editor:
            if k in ("\x1b", "L"):
                self.layout_editor = False
            elif k in (curses.KEY_UP, curses.KEY_DOWN):
                self.layout_selected = max(
                    0, min(3, self.layout_selected + (-1 if k == curses.KEY_UP else 1))
                )
            elif k in ("K", "J", getattr(curses, "KEY_SR", -999), getattr(curses, "KEY_SF", -998)):
                delta = -1 if k in ("K", getattr(curses, "KEY_SR", -999)) else 1
                i, j = self.layout_selected, self.layout_selected + delta
                if 0 <= j < len(self.order):
                    self.order[i], self.order[j] = self.order[j], self.order[i]
                    self.layout_selected = j
            elif k == "c":
                self.cover_right = not self.cover_right
            elif k == "v":
                self.show_spectrum = not self.show_spectrum
            elif k == "d":
                self.order = DEFAULT_ORDER.copy()
                self.cover_right, self.show_spectrum = False, True
            elif k in ("\n", "\r", curses.KEY_ENTER, "s"):
                self.save_layout()
                self.layout_editor = False
            return
        if self.help:
            if k in (curses.KEY_UP, curses.KEY_DOWN):
                self.help_offset = max(0, self.help_offset + (-1 if k == curses.KEY_UP else 1))
            if k in ("?", "\x1b", "q", curses.KEY_F1):
                self.help = False
            return
        if k == "\x1b" and self.search_layout:
            if self.search_scope == "context" and self.query:
                self.query = ""
                self.filter_context()
            self.leave_search_layout("library" if self.search_scope == "context" else "player")
            return
        if k == "\t":
            if self.editing:
                self.editing = False
                self.focus_panel = "library"
            else:
                self.enter_search_layout()
            return
        if self.editing:
            if k == "\x1b":
                self.editing = False
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if self.query.strip() or self.search_scope == "context":
                    self.notice = "Поиск…"
                    self.dispatch_search()
                    self.editing = False
                    self.focus_panel = "library"
            elif k == curses.KEY_DOWN and self.items:
                self.editing = False
                self.focus_panel = "library"
            elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                self.query = self.query[:-1]
                self.schedule_search()
            elif isinstance(k, str) and k.isprintable() and len(self.query) < 180:
                self.query += k
                self.schedule_search()
            return
        if self.search_layout and self.search_scope == "spotify":
            if isinstance(k, str) and k.startswith("search-category:"):
                self.select_search_category(k.split(":", 1)[1])
                return
            category_keys = {"0": "all", "1": "track", "2": "artist", "3": "album", "4": "playlist"}
            if k in category_keys:
                self.select_search_category(category_keys[k])
                return
            if k in ("n", "]"):
                self.load_more_search()
                return
        if self.artist_profile and not self.search_layout:
            if isinstance(k, str) and k.startswith("artist-group:"):
                self.select_artist_group(k.split(":", 1)[1])
                return
            groups = {"1": "album", "2": "single", "3": "appears_on", "4": "all"}
            if k in groups:
                self.select_artist_group(groups[k])
                return
        if k in ("?", curses.KEY_F1):
            self.help = True
        elif k == "L":
            if self.search_layout:
                self.leave_search_layout()
            self.fullscreen = False
            self.layout_editor = True
        elif k == "a":
            modes = ["dots", "ascii", "blocks"]
            self.art_mode = modes[(modes.index(self.art_mode) + 1) % 3] if self.art_mode in modes else "auto"
            self.save_layout()
        elif k in ("/", curses.KEY_F2):
            self.enter_search_layout()
        elif k == "q":
            self.running = False
        elif k in ("y", "Y"):
            self.share(selected=k == "Y")
        elif k == "j":
            self.share_dialog = ("SPOTIFY JAM", "Создаю Jam и получаю приглашение от Spotify…", "")
            self.submit("jam", API.start_jam)
        elif k == "f":
            track = self.playback.get("item") or {}
            if track.get("id") and track.get("type") == "track" and "favorite" not in self.pending:
                liked = "spotify:track:" + track["id"] in self.saved_tracks
                self.like_target = (track["id"], liked, track)
                self.notice = "Обновляю избранное…"
                self.submit("favorite", API.toggle_favorite, track["id"])
        elif k == "g":
            current = self.playback.get("item") or {}
            artist = next((value for value in current.get("artists", []) if value.get("id")), None)
            if artist:
                self.notice = "Загружаю страницу артиста…"
                self.submit("artist", open_artist, artist["id"], artist.get("name", "Artist"))
        elif k in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_NPAGE, curses.KEY_PPAGE):
            offset = {curses.KEY_UP: -1, curses.KEY_DOWN: 1, curses.KEY_NPAGE: 10, curses.KEY_PPAGE: -10}[k]
            self.begin_selection(self.selected + offset)
        elif k in tuple(str(i) for i in range(1, len(SECTIONS) + 1)):
            self.library(SECTIONS[int(k) - 1])
        elif k == "n" and self.search_layout:
            self.load_more_search()
        elif k in ("\n", "\r", curses.KEY_ENTER) and self.items:
            kind, item = self.items[self.selected]
            if kind == "track":
                self.start_track(item)
            elif kind == "artist":
                self.notice = "Загружаю страницу артиста…"
                self.submit("artist", open_artist, item["id"], item.get("name", "Artist"))
            elif kind in ("playlist", "album"):
                self.notice = "Загрузка треков…"
                self.submit("open", open_context, kind, item["id"], item.get("name", "Треки"))
            else:
                self.notice = "Запускаю плейлист…"
                self.submit("command", API.start_context, kind, item)
        elif k == "P" and self.items:
            kind, item = self.items[self.selected]
            if kind == "track":
                self.start_track(item)
            elif kind == "artist":
                self.notice = "Загружаю страницу артиста…"
                self.submit("artist", open_artist, item["id"], item.get("name", "Artist"))
            elif kind in ("playlist", "album"):
                self.notice = "Запускаю плейлист…"
                self.submit("command", API.start_context, kind, item)
        elif k == "o" and self.items:
            kind, item = self.items[self.selected]
            if kind == "artist":
                self.notice = "Загружаю страницу артиста…"
                self.submit("artist", open_artist, item["id"], item.get("name", "Artist"))
            elif kind in ("playlist", "album"):
                self.notice = "Загрузка треков…"
                self.submit("open", open_context, kind, item["id"], item.get("name", "Треки"))
        elif k in (curses.KEY_LEFT, curses.KEY_BACKSPACE, "\x7f", "\b") and self.history:
            self.go_back()
        elif k in ("+", "=", "-", "m"):
            self.volume_key(k)
        elif k in (" ", "n", "p", "s", "r"):
            self.command(
                "playback",
                {" ": "play-pause", "n": "next", "p": "previous", "s": "shuffle", "r": "repeat"}[k],
            )

    def run(self):
        last_poll = 0
        next_frame = 0
        dirty = True
        mouse_tracking = False
        controls = None
        self.intro_active = not NO_SPLASH
        self.intro_skip_requested = False
        self.skip_input_until = 0
        title = TerminalTitle()
        try:
            title.update({} if self.intro_active else self.playback)
            if not DEMO_MODE:
                from .control import ControlServer

                controls = ControlServer(
                    self.route_control,
                    engine_pid=getattr(getattr(API.backend, "process", None), "pid", None),
                )
                if controls.shortcut_error:
                    self.notice = "Системные F-клавиши: " + controls.shortcut_error
            # Raw mode delivers Ctrl+Q instead of consuming it as XON flow control.
            curses.raw()
            try:
                curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
                curses.mouseinterval(0 if self.intro_active else 180)
                if sys.stdout.isatty():
                    sys.stdout.write("\x1b[?1003h")
                    sys.stdout.flush()
                    mouse_tracking = True
            except curses.error:
                pass
            from .intro import Intro, FPS

            intro = (
                Intro(
                    time.monotonic(),
                    motion=not NO_MOTION,
                    art_mode=self.art_mode if self.art_mode_known else None,
                    ascii_only=ASCII_ONLY,
                )
                if self.intro_active
                else None
            )
            while self.running:
                if self.intro_active:
                    now = time.monotonic()
                    self.audio.enabled = False
                    if intro.expired(now) or self.intro_skip_requested:
                        self.finish_intro(now)
                        dirty, next_frame = True, 0
                        continue
                    if now >= next_frame:
                        intro.draw(self, now)
                        next_frame = now + 1 / FPS
                    self.s.timeout(max(1, min(33, int((next_frame - time.monotonic()) * 1000))))
                    try:
                        key = self.s.get_wch()
                        if key == curses.KEY_RESIZE:
                            intro.size = None
                            next_frame = 0
                        elif self.intro_key(key):
                            self.finish_intro(time.monotonic())
                            dirty, next_frame = True, 0
                    except curses.error:
                        pass
                    continue
                dirty = self.drain() or dirty
                title.update(self.playback)
                now = time.monotonic()
                self.audio.enabled = (self.show_spectrum or self.fullscreen) and not (
                    self.help or self.layout_editor or self.share_dialog
                )
                self.prefetch_nearby()
                self.update_live_search()
                if now - last_poll > (0.1 if getattr(API, "local_controls", False) else 2):
                    self.submit("poll", cli, "get", "key", "playback")
                    last_poll = time.monotonic()
                if now >= next_frame:
                    if dirty:
                        self.render()
                        dirty = False
                    else:
                        self.animate()
                    motion_active = bool(
                        self.panel_transition or self.art_transition or self.selection_transition
                    )
                    if self.low_power:
                        interval = 1 / 12 if self.audio.enabled else 1 / 6
                    else:
                        interval = 1 / 30 if self.audio.enabled or (motion_active and self.motion_enabled) else 1 / 8
                    next_frame = now + interval
                timeout_max = 83 if self.low_power else 33
                self.s.timeout(max(1, min(timeout_max, int((next_frame - time.monotonic()) * 1000))))
                try:
                    key = self.s.get_wch()
                    if time.monotonic() < self.skip_input_until:
                        continue
                    self.key(key)
                    if key != curses.KEY_MOUSE or self.mouse_changed:
                        dirty = True
                        next_frame = 0
                except curses.error:
                    pass
        finally:
            self.intro_active = False
            title.close()
            if controls:
                controls.close()
            self.checkpoint()
            if mouse_tracking:
                sys.stdout.write("\x1b[?1003l")
                sys.stdout.flush()
            try:
                curses.mousemask(0)
            except curses.error:
                pass
            self.audio.close()
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.transport_pool.shutdown(wait=False, cancel_futures=True)
            self.state_pool.shutdown(wait=False, cancel_futures=True)
            self.search_pool.shutdown(wait=False, cancel_futures=True)
            self.art_pool.shutdown(wait=False, cancel_futures=True)
            self.cover_pool.shutdown(wait=False, cancel_futures=True)


class _IntroRenderer(App):
    """Small renderer for the startup screen; it starts no Spotify/API workers."""

    def __init__(self, screen):
        self.s = screen
        self.colors = {}
        self.next_color = 20
        self.dot_cache = OrderedDict()
        self.default_background = -1
        self._panel_x = 0
        self._panel_width = screen.getmaxyx()[1]
        # Required by put() and symbol_image()
        self._render_grid = None
        self._display_grid = None
        try:
            screen.encoding = "utf-8"
        except (AttributeError, TypeError):
            pass
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error:
            self.default_background = 0
        # Initialize all color pairs used by symbol_image/dot_image and put()
        for i, fg, bg in [
            (1, 252, -1),
            (2, 78, -1),
            (3, 110, -1),
            (4, 244, -1),
            (5, 222, -1),
            (6, 255, 236),
            (7, 147, -1),
            (8, 210, -1),
            (9, 255, 235),
            (10, 110, 235),
            (11, 239, -1),
            (12, 78, 236),
        ]:
            self.init_pair(i, fg, bg)
        # Don't call bkgd() - it forces a background color even with use_default_colors()
        # and breaks terminal transparency on Windows PDCurses.
        # Let the terminal handle background (transparency, Acrylic, images, themes).
        # Basic curses setup for proper rendering
        try:
            screen.keypad(True)
            curses.curs_set(0)
            screen.timeout(16)
        except curses.error:
            pass


def startup_screen(screen, start, *, status=None, cancel=None):
    """Show the system-info intro while the Spotify engine starts, then hold briefly."""
    from .intro import DURATION, FPS, READY_HOLD, Intro

    started = time.monotonic()
    renderer = _IntroRenderer(screen)
    intro = Intro(started, motion=not NO_MOTION, art_mode="ascii" if ASCII_ONLY else "dots", ascii_only=ASCII_ONLY)
    done = threading.Event()
    result = {"error": None, "finished": None}

    def initialize():
        try:
            start()
        except BaseException as error:
            result["error"] = error
        finally:
            result["finished"] = time.monotonic()
            done.set()

    worker = threading.Thread(target=initialize, name="tspotify-startup", daemon=True)
    worker.start()
    next_frame = started
    try:
        while True:
            now = time.monotonic()
            if result["error"]:
                intro.status = "Не удалось загрузить клиент Spotify"
            elif done.is_set():
                intro.status = "Spotify готов · открываем плеер"
            else:
                intro.status = status() if status else "Подключаем клиент Spotify…"
            if (
                done.is_set()
                and now >= started + DURATION
                and now >= result["finished"] + READY_HOLD
            ):
                break
            if now >= next_frame:
                intro.draw(renderer, now)
                next_frame = now + 1 / FPS
            screen.timeout(max(1, min(50, int((next_frame - time.monotonic()) * 1000))))
            try:
                key = screen.get_wch()
                if key == curses.KEY_RESIZE:
                    intro.size = None
                    next_frame = 0
            except curses.error:
                pass
    except BaseException:
        if cancel:
            cancel()
        worker.join(timeout=5)
        raise
    worker.join()
    return result["error"]
