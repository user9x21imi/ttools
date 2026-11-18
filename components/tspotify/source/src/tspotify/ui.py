"""Curses interface. The same dotted renderer runs in Windows Terminal, macOS and Linux."""

import concurrent.futures
from collections import OrderedDict
import curses
import json
import math
import queue
import sys
import time

from . import paths
from .api import RateLimited
from .art import cover, logo, thumbnail, image_url
from .audio import Audio

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


class App:
    def __init__(self, screen):
        self.s = screen
        try:
            self.s.encoding = "utf-8"
        except (AttributeError, TypeError):
            pass
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.art_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.cover_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.transport_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
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
        self.art_url = ""
        self.art = []
        self.dot_cache = OrderedDict()
        self.art_mode = "dots"
        self.native_supported = False
        self.native_last = None
        self.native_area = None
        self.smooth_bars = [0.0] * 32
        self.smooth_time = time.monotonic()
        self.query = ""
        self.editing = False
        self.help = False
        self.help_offset = 0
        self.layout_editor = False
        self.fullscreen = False
        self.focus_panel = "library"
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
            if self.art_mode not in ("dots", "ascii", "blocks"):
                self.art_mode = "dots"
        except (OSError, ValueError):
            pass
        if ASCII_ONLY:
            self.art_mode = "ascii"
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
        self.s.bkgd(" ", curses.color_pair(1) if curses.has_colors() else 0)
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
        if key == "command":
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

        pool = self.cover_pool if key == "cover" else self.art_pool if key.startswith("thumb:") else self.pool
        if key in ("volume", "command"):
            pool = self.transport_pool
        pool.submit(run)

    def library(self, section):
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
            if key == "notice":
                self.notice = value
                continue
            if key.startswith("thumb:"):
                self.thumbnails[key[6:]] = value or []
                while len(self.thumbnails) > 128:
                    self.thumbnails.popitem(last=False)
                continue
            if error:
                if key.startswith("library:"):
                    self.library_requested.discard(key[8:])
                if key == "poll" and API.backend and ("Connection refused" in error or "timed out" in error):
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
                same = (old.get("item") or {}).get("id") == (incoming.get("item") or {}).get("id")
                if same and old.get("is_playing") and incoming.get("is_playing"):
                    expected = (old.get("progress_ms") or 0) + max(0, now - self.updated) * 1000
                    actual = incoming.get("progress_ms") or 0
                    if abs(actual - expected) < 2500:
                        incoming = {**incoming, "progress_ms": expected}
                self.playback = incoming
                self.updated = now
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
            elif key == "cover":
                url, image = value
                if url == self.art_url:
                    self.art = image
                elif self.art_url:
                    self.submit("cover", lambda u=self.art_url: (u, cover(u, 256, 256)))
            elif key == "search":
                self.section = "Поиск: " + self.query
                self.items = []
                for kind, name in [
                    ("track", "tracks"),
                    ("album", "albums"),
                    ("artist", "artists"),
                    ("playlist", "playlists"),
                ]:
                    self.items.extend((kind, item) for item in (value or {}).get(name, []) if item)
                self.selected = 0
                self.restore_selected_row()
                self.notice = f"Найдено: {len(self.items)} · Enter — слушать"
            elif key == "open":
                data = value or {}
                if "Playlist" in data or "Album" in data:
                    data = data.get("Playlist", data.get("Album"))
                tracks = data.get("tracks", [])
                if isinstance(tracks, dict):
                    tracks = tracks.get("items", [])
                self.history.append((self.section, self.items, self.selected))
                self.section = (data.get("playlist") or data.get("album") or data).get("name", "Треки")
                for track in tracks:
                    if isinstance(track, dict):
                        track["_context_uri"] = data.get("context_uri")
                self.items = [
                    ("track", x["track"] if isinstance(x.get("track"), dict) else x)
                    for x in tracks
                    if isinstance(x, dict) and x.get("id", x.get("track"))
                ]
                self.selected = 0
                self.restore_selected_row()
                self.notice = f"Треков: {len(self.items)} · Enter слушать · ← назад"
            elif key == "command":
                self.transport_revision += 1
                if getattr(API, "local_controls", False) and getattr(API, "last_playback", None):
                    self.playback = dict(API.last_playback)
                    self.updated = time.monotonic()
                self.notice = value if isinstance(value, str) else "Команда подтверждена"
                self.track_cover((getattr(API, "last_playback", {}) or {}).get("item") or {})
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
        if y < 0 or y >= h or x < 0 or x >= w:
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
        try:
            self.s.addnstr(
                y,
                x,
                text,
                max(0, min(w - x - 1, width or w)),
                (curses.color_pair(color) if curses.has_colors() else 0) | (curses.A_BOLD if bold else 0),
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

    def dot_image(self, image, y, x, width, height, logo=False):
        cache_key = (id(image), width, height, logo)
        cached_cells = self.dot_cache.get(cache_key)
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
        self.hits.append((y, x, height, width, action, value))

    def button(self, y, x, text, key):
        self.put(y, x, text, 3)
        self.hit(y, x, 1, len(text), "key", key)

    def button_row(self, y, w, actions, x=3):
        for text, key in actions:
            if x + len(text) > w - 2:
                break
            self.button(y, x, text, key)
            x += len(text) + 1

    def transport(self, y, w):
        active = self.playback.get("is_playing", False)
        self.button_row(
            y,
            w,
            [
                ("[-]", "-"),
                ("[+]", "+"),
                ("[Space Пауза]" if active else "[Space Играть]", " "),
                ("[m Звук]", "m"),
                ("[p Назад]", "p"),
                ("[n Далее]", "n"),
                ("[f ♥]", "f"),
            ],
        )

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
        for by, bx, height, width, action, value in reversed(self.hits):
            if not (by <= y < by + height and bx <= x < bx + width):
                continue
            if action in ("row", "panel"):
                panel = "library" if action == "row" else value
                self.mouse_changed |= self.focus_panel != panel
                self.focus_panel = panel
                if wheel_up or wheel_down:
                    if self.focus_panel == "library":
                        self.selected = max(
                            0, min(len(self.items) - 1, self.selected + (-3 if wheel_up else 3))
                        )
                    return
            if not clicked:
                continue
            if action == "row":
                self.editing = False
                self.selected = value
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
        self.put(1, 4, "NOW PLAYING · точечная обложка · F3 / Esc свернуть", 2, width=w - 8)
        self.progress_area = self.spectrum_area = None
        art_h = max(4, min((w - 12) // 2, h - 19))
        art_w = art_h * 2
        ax = (w - art_w) // 2
        self.box(2, ax - 2, art_h + 2, art_w + 4, "ASCII · NOW PLAYING", True)
        if self.art:
            if ASCII_ONLY:
                # Keep the explicit font fallback in the expanded view too.
                ramp = " .:-=+*#%@"
                for yy in range(art_h):
                    row = self.art[min(len(self.art) - 1, yy * len(self.art) // art_h)]
                    for xx in range(art_w):
                        rgb = row[min(len(row) - 1, xx * len(row) // art_w)]
                        self.put(3 + yy, ax + xx, ramp[min(9, int(sum(rgb) / 765 * 9))], 3)
            else:
                self.dot_image(self.art, 3, ax, art_w, art_h)
        else:
            self.put(3 + art_h // 2, ax, "Загружаю обложку…", 4, width=art_w)
        item = self.playback.get("item") or {}
        title_y = art_h + 5
        self.put(title_y, 4, item.get("name", "Выберите трек в библиотеке"), 1, True, width=w - 8)
        self.put(
            title_y + 1, 4, artists(item) + " · " + (item.get("album") or {}).get("name", ""), 3, width=w - 8
        )
        active = self.playback.get("is_playing", False)
        self.put(title_y + 2, 4, "● ИГРАЕТ" if active else "Ⅱ ПАУЗА · Space продолжить", 2 if active else 5)
        total = item.get("duration_ms") or 0
        ms = min(
            total,
            (self.playback.get("progress_ms") or 0)
            + ((time.monotonic() - self.updated) * 1000 if active else 0),
        )
        width = w - 25
        filled = int(width * ms / total) if total else 0
        self.progress_area = (title_y + 3, 4, width)
        self.hit(title_y + 3, 4, 1, width, "seek", None)
        self.put(title_y + 3, 4, "━" * filled + "─" * (width - filled), 2)
        self.put(title_y + 3, width + 6, f"{duration(ms)} / {duration(total)}", 4)
        self.transport(title_y + 5, w)
        sy = title_y + 7
        self.put(sy - 1, 4, "Спектр Spotify · " + self.audio.status, 4, width=w - 8)
        self.spectrum_area = (sy, 4, max(1, h - sy - 3), w - 8)
        self.spectrum(*self.spectrum_area)
        self.put(
            h - 2, 4, f"Громкость {self.volume}% · ± / F11/F12 · F3/Esc назад · Ctrl+Q выход", 3, width=w - 8
        )
        self.put(h - 1, 4, self.notice, 4, width=w - 8)

    def render(self):
        self.hits = []
        self.s.erase()
        h, w = self.s.getmaxyx()
        if h < 24 or w < 78:
            self.spectrum_area = None
            self.progress_area = None
            self.put(1, 2, "Увеличьте терминал: минимум 78 × 24", 5)
            self.put(3, 2, "q — выход")
            self.s.refresh()
            return
        self.put(0, 2, "● tspotify", 2, True)
        self.put(0, 16, "DEMO / NO AUDIO" if DEMO_MODE else "YOUR MUSIC, LESS NOISE", 5 if DEMO_MODE else 4)
        self.button(0, w - 43, "[F3 Плеер]", curses.KEY_F3)
        self.button(0, w - 31, "[L Окна]", "L")
        self.button(0, w - 21, "[? Клавиши]", "?")
        if self.fullscreen:
            self.render_fullscreen(h, w)
            if self.help:
                self.render_help(h, w)
            curses.curs_set(0)
            self.s.refresh()
            return
        player_h = (
            6
            if h < 25
            else 7
            if h < 27
            else 8
            if h < 30
            else (24 if h >= 58 else (20 if h >= 46 else (16 if h >= 40 else (13 if h >= 35 else 11))))
        )
        spectrum_h = (6 if h >= 43 else 4) if self.show_spectrum and h >= 35 else 0
        count = 4 if spectrum_h else 3
        available = h - 8 - (count - 1)
        heights = {
            "search": 3,
            "player": player_h,
            "spectrum": spectrum_h,
            "library": max(4, available - 3 - player_h - spectrum_h),
        }
        y = 2
        for name in self.order:
            if heights[name]:
                getattr(self, "render_" + name)(y, w, heights[name])
                y += heights[name] + 1
        self.box(
            h - 5,
            1,
            4,
            w - 2,
            "БЕЗ ЗВУКА · + / F12 громче · F10"
            if not self.volume
            else "Громкость · − / + · F11/F12 · F10 mute",
        )
        self.hit(h - 4, 3, 1, 16, "volume", None)
        filled = round(self.volume * 16 / 100)
        self.put(h - 4, 3, "━" * filled + "─" * (16 - filled), 2)
        self.put(h - 4, 21, f"{self.volume:3d}%", 1, True)
        self.put(h - 4, 30, self.notice, 4, width=w - 34)
        self.transport(h - 3, w)
        self.button_row(
            h - 1,
            w,
            [
                ("[Enter ▶]", "\n"),
                ("[/ Поиск]", "/"),
                ("[← Назад]", curses.KEY_LEFT),
                ("[P Плейлист]", "P"),
                ("[? Помощь]", "?"),
                ("[Ctrl+Q Выход]", "\x11"),
            ],
        )
        if self.help:
            self.render_help(h, w)
        if self.layout_editor:
            self.render_layout(h, w)
        if self.editing and not self.help and not self.layout_editor:
            curses.curs_set(1)
            self.s.move(self.search_y, min(w - 4, 5 + len(self.query)))
        else:
            curses.curs_set(0)
        self.s.refresh()

    def render_search(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "search")
        self.box(y, 1, height, w - 2, "Поиск · / или F2", self.editing or self.focus_panel == "search")
        self.search_y = y + 1
        self.put(y + 1, 3, "›", 2)
        hint = "Трек, исполнитель, альбом или плейлист…"
        self.put(y + 1, 5, self.query or hint, 1 if self.editing else 4, width=w - 9)

    def render_player(self, y, w, height):
        mode = {"dots": "ASCII · DOTS", "ascii": "ASCII", "blocks": "PIXEL"}.get(
            self.art_mode, "ASCII · DOTS"
        )
        self.hit(y, 1, height, w - 2, "panel", "player")
        self.box(y, 1, height, w - 2, "Сейчас играет · " + mode, self.focus_panel == "player")
        self.button(y, w - 20, "[F3 Развернуть]", curses.KEY_F3)
        art_h = height - 4
        art_w = art_h * 2
        ax = w - art_w - 4 if self.cover_right else 3
        x = 3 if self.cover_right else art_w + 7
        width = w - art_w - 12
        new_area = (y + 2, ax, art_w, art_h)
        self.native_area = new_area
        self.hit(y + 2, ax, art_h, art_w, "key", curses.KEY_F3)
        if self.art and self.art_mode == "dots":
            self.dot_image(self.art, y + 2, ax, art_w, art_h)
        elif self.art:
            rows, cols = len(self.art), len(self.art[0])
            for yy in range(art_h):
                for xx in range(art_w):
                    top = self.art[min(rows - 1, yy * 2 * rows // (art_h * 2))][
                        min(cols - 1, xx * cols // art_w)
                    ]
                    bottom = self.art[min(rows - 1, (yy * 2 + 1) * rows // (art_h * 2))][
                        min(cols - 1, xx * cols // art_w)
                    ]
                    if self.art_mode == "ascii":
                        ramp = " .:-=+*#%@"
                        lum = (0.2126 * top[0] + 0.7152 * top[1] + 0.0722 * top[2]) / 255
                        self.put(
                            y + 2 + yy,
                            ax + xx,
                            ramp[min(9, int(lum * 9))],
                            self.pixel_color(top, (18, 18, 18)),
                        )
                    else:
                        self.put(y + 2 + yy, ax + xx, "▀", self.pixel_color(top, bottom))
        elif not self.art:
            self.put(y + height // 2, ax + 2, "♪  Загружаю…", 4)
        item = self.playback.get("item") or {}
        active = self.playback.get("is_playing", False)
        liked = "spotify:track:" + str(item.get("id")) in self.saved_tracks
        self.hit(y + (1 if height < 11 else 2), x, 1, min(width, 20), "key", " ")
        self.hit(y + height - 2, x, 1, width, "key", "f")
        self.put(
            y + (1 if height < 11 else 2),
            x,
            "● ВОСПРОИЗВЕДЕНИЕ" if active else "Ⅱ ПАУЗА",
            2 if active else 5,
            width=width,
        )
        self.put(
            y + (2 if height < 11 else 4),
            x,
            item.get("name", "Выберите музыку в библиотеке"),
            1,
            True,
            width=width,
        )
        if height >= 7:
            self.put(y + (3 if height < 11 else 5), x, artists(item), 3, width=width)
        if height >= 8:
            self.put(
                y + (4 if height < 11 else 6), x, (item.get("album") or {}).get("name", ""), 7, width=width
            )
        progress = (self.playback.get("progress_ms") or 0) + (
            (time.monotonic() - self.updated) * 1000 if active else 0
        )
        total = item.get("duration_ms") or 0
        progress = min(progress, total)
        bar_w = max(8, width - 17)
        progress_y = y + height - (3 if height < 11 else 4)
        self.progress_area = (progress_y, x, bar_w)
        self.hit(progress_y, x, 1, bar_w, "seek", None)
        filled = int(bar_w * progress / total) if total else 0
        self.put(progress_y, x, "━" * filled, 2)
        self.put(progress_y, x + filled, "─" * (bar_w - filled), 11)
        self.put(progress_y, x + bar_w + 2, f"{duration(progress)} / {duration(total)}", 4)
        self.put(
            y + height - 2,
            x,
            "♥ В избранном · f убрать" if liked else "♡ Добавить в избранное · f",
            8 if liked else 4,
            width=width,
        )
        if height >= 17:
            device = (self.playback.get("device") or {}).get("name", "tspotify")
            self.put(y + 8, x, "Устройство: " + device, 4, width=width)
            self.button_row(
                y + 9,
                x + width + 2,
                [
                    (
                        "[s ⇄ "
                        + ("Перемешивание" if self.playback.get("shuffle_state") else "По порядку")
                        + "]",
                        "s",
                    ),
                    ("[r ↻ " + str(self.playback.get("repeat_state", "off")) + "]", "r"),
                ],
                x=x,
            )

    def render_spectrum(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "spectrum")
        self.box(
            y, 1, height, w - 2, "Спектр · Spotify · " + self.audio.status, self.focus_panel == "spectrum"
        )
        self.spectrum(y + 1, 4, height - 2, w - 8)
        self.spectrum_area = (y + 1, 4, height - 2, w - 8)

    def animate(self):
        if self.help or self.layout_editor:
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
            self.s.move(self.search_y, min(self.s.getmaxyx()[1] - 4, 5 + len(self.query)))
        self.s.refresh()

    def render_library(self, y, w, height):
        self.hit(y, 1, height, w - 2, "panel", "library")
        self.box(y, 1, height, w - 2, "Библиотека · " + self.section, self.focus_panel == "library")
        tx, ty = 3, y + 1
        for index, section in enumerate(SECTIONS, 1):
            text = f" {index} {section} "
            if tx + len(text) > w - 3:
                tx, ty = 3, ty + 1
            self.put(ty, tx, text, 12 if self.section == section else 4)
            self.hit(ty, tx, 1, len(text), "key", str(index))
            tx += len(text) + 1
        list_y = ty + 1
        thumbs = bool(self.items and self.items[0][0] in ("playlist", "album")) and height >= 7
        row_h = 3 if thumbs else 1
        rows = max(1, (y + height - 1 - list_y) // row_h)
        start = max(0, self.selected - rows + 1)
        self.list_area = (list_y, rows)
        for row, (kind, data) in enumerate(self.items[start : start + rows]):
            selected = start + row == self.selected
            yy = list_y + row * row_h
            self.hit(yy, 3, row_h, w - 6, "row", start + row)
            label = {"track": "ТРЕК", "album": "АЛЬБОМ", "artist": "АРТИСТ", "playlist": "ПЛЕЙЛИСТ"}.get(
                kind, kind
            )
            if kind == "track":
                milliseconds = data.get("duration_ms") or 0
                if not milliseconds and isinstance(data.get("duration"), dict):
                    milliseconds = data["duration"].get("secs", 0) * 1000
                label = duration(milliseconds) if milliseconds else "--:--"
            if selected:
                for dy in range(row_h):
                    self.put(yy + dy, 3, " " * (w - 6), 6)
            self.put(yy + row_h // 2, 3, "›" if selected else " ", 12 if selected else 4)
            tx = 5
            if thumbs:
                key = kind + ":" + data["id"]
                image = self.thumbnails.get(key)
                if image:
                    self.thumbnails.move_to_end(key)
                    if ASCII_ONLY:
                        self.put(yy + 1, 5, "[ART]", 3)
                    else:
                        self.dot_image(image, yy, 5, 6, 3)
                else:
                    self.put(yy + 1, 5, "······", 11)
                    thumb_jobs = sum(x.startswith("thumb:") for x in self.pending)
                    if key not in self.thumbnails and thumb_jobs < 4:
                        self.submit("thumb:" + key, self.load_thumbnail, kind, data)
                tx = 13
            owner = data.get("owner") or [""]
            by = artists(data) or (
                owner[0]
                if isinstance(owner, list)
                else owner.get("display_name", "")
                if isinstance(owner, dict)
                else ""
            )
            self.put(
                yy,
                tx,
                data.get("name", ""),
                6 if selected else 1,
                selected,
                width=w - tx - 18 if thumbs else int((w - 20) * 0.55),
            )
            if thumbs:
                self.put(yy + 1, tx, by, 6 if selected else 3, width=w - tx - 18)
            else:
                self.put(yy, int(w * 0.57), by, 6 if selected else 3, width=max(4, int(w * 0.27)))
            self.put(yy, w - 14, label, 6 if selected else 4)
        if not self.items:
            self.put(list_y, 4, "Пусто · / поиск · 1–8 разделы библиотеки", 4)

    def load_thumbnail(self, kind, item):
        images = item.get("images") or (item.get("album") or {}).get("images") or []
        if images:
            return cover(images[-1]["url"], 24, 24)
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

    def splash(self):
        h, w = self.s.getmaxyx()
        self.s.erase()
        x, y = max(2, (w - 78) // 2), max(1, (h - 17) // 2)
        if ASCII_ONLY:
            for i, line in enumerate(
                [
                    "     .------------.",
                    "   /    ~~~~~~~~    \\",
                    "  |      ~~~~~~      |",
                    "   \\      ~~~~     /",
                    "     `------------`",
                ]
            ):
                self.put(y + i + 3, x, line, 2, True)
        else:
            self.dot_image(logo(), y, x, 28, 14, logo=True)
        self.put(y + 1, x + 34, "tspotify", 2, True)
        self.put(y + 2, x + 34, "----------------------------", 11)
        for i, (label, value) in enumerate(
            [
                ("Клиент", "Spotify Connect"),
                ("Обложки", "ASCII DOTS / 256 x 256"),
                ("Спектр", "FFT / плавные 30 fps"),
                ("Поиск", "/ или F2"),
                ("Громкость", "+ / -"),
                ("Избранное", "f / добавить и убрать"),
                ("Окна", "L / своя раскладка"),
                ("Справка", "? или F1"),
            ]
        ):
            self.put(y + 4 + i, x + 34, label, 3, width=11)
            self.put(y + 4 + i, x + 47, value, 1)
        self.put(y + 15, x + 5, "Загружаем вашу музыку...", 4)
        self.s.refresh()
        time.sleep(2)
        self.s.clear()
        self.s.refresh()

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

    def render_help(self, h, w):
        self.hits = []
        lines = [
            ("/ или F2", "Ввести поисковый запрос"),
            ("Enter в поиске", "Найти музыку"),
            ("Enter в списке", "Открыть плейлист / включить трек"),
            ("P", "Включить весь плейлист / альбом"),
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
            ("s / r", "Перемешивание / повтор"),
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
        if "command" not in self.pending:
            if not getattr(API, "local_controls", False):
                self.notice = "Выполняю…"
            self.submit("command", cli, *args)

    def track_cover(self, item):
        images = (item.get("album") or {}).get("images") or item.get("images") or []
        url = image_url(images, 256)
        if url != self.art_url:
            self.art_url, self.art = url, []
            if url:
                self.submit("cover", lambda u=url: (u, cover(u, 256, 256)))

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
        if k == curses.KEY_F3:
            self.fullscreen = not self.fullscreen
            self.editing = self.help = self.layout_editor = False
            return
        if k == "\x1b" and self.fullscreen:
            self.fullscreen = False
            return
        if k == curses.KEY_RESIZE:
            self.s.clear()
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
        if k == "\t":
            self.editing = not self.editing
            return
        if self.editing:
            if k == "\x1b":
                self.editing = False
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if self.query.strip():
                    self.notice = "Поиск…"
                    self.submit("search", cli, "search", self.query.strip())
                    self.editing = False
            elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                self.query = self.query[:-1]
            elif isinstance(k, str) and k.isprintable() and len(self.query) < 180:
                self.query += k
            return
        if k in ("?", curses.KEY_F1):
            self.help = True
        elif k == "L":
            self.fullscreen = False
            self.layout_editor = True
        elif k == "a":
            modes = ["dots", "ascii", "blocks"]
            self.art_mode = modes[(modes.index(self.art_mode) + 1) % 3] if self.art_mode in modes else "auto"
            self.save_layout()
        elif k in ("/", curses.KEY_F2):
            self.fullscreen = False
            self.editing = True
        elif k == "q":
            self.running = False
        elif k == "f":
            track = self.playback.get("item") or {}
            if track.get("id") and track.get("type") == "track" and "favorite" not in self.pending:
                liked = "spotify:track:" + track["id"] in self.saved_tracks
                self.like_target = (track["id"], liked, track)
                self.notice = "Обновляю избранное…"
                self.submit("favorite", API.toggle_favorite, track["id"])
        elif k in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_NPAGE, curses.KEY_PPAGE):
            offset = {curses.KEY_UP: -1, curses.KEY_DOWN: 1, curses.KEY_NPAGE: 10, curses.KEY_PPAGE: -10}[k]
            self.selected = max(0, min(len(self.items) - 1, self.selected + offset))
        elif k in tuple(str(i) for i in range(1, len(SECTIONS) + 1)):
            self.library(SECTIONS[int(k) - 1])
        elif k in ("\n", "\r", curses.KEY_ENTER) and self.items:
            kind, item = self.items[self.selected]
            if kind == "track":
                self.notice = "Запускаю и проверяю трек…"
                self.submit("command", API.start, item)
            elif kind in ("playlist", "album", "artist"):
                self.notice = "Загрузка треков…"
                self.submit("open", open_context, kind, item["id"], item.get("name", "Треки"))
            else:
                self.notice = "Запускаю плейлист…"
                self.submit("command", API.start_context, kind, item)
        elif k == "P" and self.items:
            kind, item = self.items[self.selected]
            if kind in ("playlist", "album", "artist"):
                self.notice = "Запускаю плейлист…"
                self.submit("command", API.start_context, kind, item)
        elif k == "o" and self.items:
            kind, item = self.items[self.selected]
            if kind in ("playlist", "album"):
                self.notice = "Загрузка треков…"
                self.submit("open", open_context, kind, item["id"], item.get("name", "Треки"))
        elif k in (curses.KEY_LEFT, curses.KEY_BACKSPACE, "\x7f", "\b") and self.history:
            self.section, self.items, self.selected = self.history.pop()
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
        try:
            if not DEMO_MODE:
                from .control import ControlServer

                controls = ControlServer(
                    lambda action: self.events.put(("hotkey", action, None)),
                    engine_pid=getattr(getattr(API.backend, "process", None), "pid", None),
                )
                if controls.shortcut_error:
                    self.notice = "Системные F-клавиши: " + controls.shortcut_error
            # Raw mode delivers Ctrl+Q instead of consuming it as XON flow control.
            curses.raw()
            try:
                curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
                curses.mouseinterval(180)
                if sys.stdout.isatty():
                    sys.stdout.write("\x1b[?1003h")
                    sys.stdout.flush()
                    mouse_tracking = True
            except curses.error:
                pass
            if not NO_SPLASH:
                self.submit("poll", cli, "get", "key", "playback")
                self.splash()
            while self.running:
                dirty = self.drain() or dirty
                now = time.monotonic()
                self.audio.enabled = (self.show_spectrum or self.fullscreen) and not (
                    self.help or self.layout_editor
                )
                if now - last_poll > 2:
                    self.submit("poll", cli, "get", "key", "playback")
                    last_poll = time.monotonic()
                if now >= next_frame:
                    if dirty:
                        self.render()
                        dirty = False
                    else:
                        self.animate()
                    next_frame = now + (1 / 30 if self.audio.enabled else 1 / 8)
                self.s.timeout(max(1, min(33, int((next_frame - time.monotonic()) * 1000))))
                try:
                    key = self.s.get_wch()
                    self.key(key)
                    if key != curses.KEY_MOUSE or self.mouse_changed:
                        dirty = True
                except curses.error:
                    pass
        finally:
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
            self.art_pool.shutdown(wait=False, cancel_futures=True)
            self.cover_pool.shutdown(wait=False, cancel_futures=True)
