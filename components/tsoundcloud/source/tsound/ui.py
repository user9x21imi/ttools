from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import curses
from dataclasses import asdict
from itertools import permutations
from queue import Empty, SimpleQueue
import os
import platform
import random
import shutil
import subprocess
from textwrap import wrap
from threading import Event
from urllib.parse import urlsplit
import webbrowser
import time
import unicodedata

from . import state
from .audio import Playback
from .demo import DemoPlayback
from .service import Entry, unique, waveform
from .web_service import WebSoundCloud, numeric
from .visual import (Timeline, clock, column, decoded_waveform, demo_pixels, dots,
                     peaks, pixels)


TABS = {
    "recent": "Недавние треки", "artists": "Недавние исполнители", "mixes": "Миксы",
    "feed": "Лента", "likes": "Любимые", "playlists": "Плейлисты",
    "uploads": "Мои треки", "apps": "Приложения",
}
KINDS = {"album": "Альбом", "playlist": "Плейлист", "station": "Микс", "user": "Исполнитель"}
SCOPES = {"album": "В этом альбоме", "playlist": "В этом плейлисте",
          "station": "В этом миксе", "user": "У этого исполнителя"}
ORANGE, WHITE, DIM, GREEN, ERROR = 1, 2, 3, 4, 5
FUNCTION_ESC = {f"[{code}~": curses.KEY_F0 + index for index, code in
                enumerate((18, 19, 20, 21, 23, 24), 7)}
ORDERS = list(permutations(("player", "spectrum", "list")))


def clean(value):
    return "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Cs") else c for c in str(value))


def cell_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def matches(entries, query):
    words = query.casefold().split()
    return [entry for entry in entries if all(word in
            " ".join((entry.title, entry.artist, entry.release)).casefold() for word in words)]


class App:
    def __init__(self, screen, service, demo=False, ascii_mode=False, splash=False):
        self.screen = screen
        self.service = service
        self.demo = demo
        self.ascii = ascii_mode
        self.splash = time.monotonic() + 2.5 if splash else 0
        self.pools = {name: ThreadPoolExecutor(max_workers=count) for name, count in
                      (("browse", 4), ("search", 2), ("art", 3), ("meta", 3), ("wave", 1), ("stream", 2))}
        self.events = SimpleQueue()
        self.tabs = {}
        self.tab_errors = {}
        self.library_generation = 0
        self.favorite_keys = None
        self.favorite_complete = False
        self.favorite_pending = set()
        self.loading = set()
        self.covers = OrderedDict()
        self.cover_loading = set()
        self.colors = {}
        self.tab = "recent"
        self.context = None
        self.context_items = []
        self.stack = []
        self.browse_version = 0
        self.searching = False
        self.editing = False
        self.global_search = False
        self.query = ""
        self.search_version = 0
        self.search_due = 0
        self.search_results = []
        self.search_futures = []
        self.search_cache = OrderedDict()
        self.selected = self.top = 0
        self.library_view = False
        self.login = False
        self.login_attempt = None
        self.login_error = ""
        self.login_status = ""
        self.full = self.help = self.layout = False
        self.notice = ""
        self.error = ""
        self.track = None
        self.timeline = Timeline()
        self.comment_status = ""
        self.samples = []
        self.wave_ready = False
        self.wave_cancel = Event()
        self.wave_task = None
        self.wave_cache = OrderedDict()
        self.levels = [0.] * 15
        self.player = None
        self.retiring = None
        self.stream_url = ""
        self.stream_valid_until = 0
        self.play_status = self.play_error = ""
        self.stream_future = None
        self.preview = False
        self.want_pause = True
        self.position = 0.
        self.pending_position = None
        self.play_version = 0
        self.queue = []
        self.original_queue = []
        self.queue_index = 0
        self.recorded = None
        self.dragging = False
        self.hits = []
        self.wave_hit = None
        self.mouse_position = None
        self.page = 1
        self.muted = False
        self.running = True
        session = {} if demo else state.read("session.json")
        self.shuffle = bool(session.get("shuffle", False))
        self.repeat = session.get("repeat", "off")
        if self.repeat not in ("off", "all", "one"):
            self.repeat = "off"
        self.volume = min(100, max(0, int(session.get("volume", 65))))
        self.order = int(session.get("order", 0)) % len(ORDERS)
        self.right_art = session.get("right_art", True)
        self.show_spectrum = session.get("spectrum", True)
        self.tab = session.get("tab", "recent")
        if self.tab not in TABS:
            self.tab = "recent"
        if not demo and not service.signed_in:
            self.login = True
        else:
            self.load_tab(self.tab)
        if session.get("context"):
            self.open_collection(Entry(**session["context"]))
        if session.get("track"):
            queue = [Entry(**item) for item in session.get("queue", [])]
            track = Entry(**session["track"])
            self.original_queue = [Entry(**item) for item in session.get("original_queue", [])] or queue or [track]
            self.choose(track, queue or [track], paused=True, offset=session.get("position", 0))
        elif demo:
            self.original_queue = service.tracks[:]
            self.choose(service.tracks[0], service.tracks, paused=True)

    def submit(self, pool, callback, operation, *args):
        future = self.pools[pool].submit(operation, *args)

        def done(result):
            if result.cancelled():
                return
            try:
                value = result.result()
            except Exception as error:
                self.events.put((callback, None, clean(error)))
            else:
                self.events.put((callback, value, ""))

        future.add_done_callback(done)
        return future

    def load_tab(self, tab, refresh=False):
        if tab == "apps" or tab in self.loading or (
                tab in self.tabs and tab not in self.tab_errors and not refresh):
            return
        self.loading.add(tab)
        self.tab_errors.pop(tab, None)
        generation = self.library_generation
        progressive = isinstance(self.service, WebSoundCloud) and tab in ("playlists", "uploads", "feed")

        def publish_favorites(items):
            self.tabs["likes"] = items
            self.favorite_keys = {numeric(item.key) for item in items}

        def partial(items, _):
            if generation == self.library_generation and items and not self.favorite_complete:
                publish_favorites(items)

        def add_page(items, _):
            if generation == self.library_generation and items:
                self.tabs[tab] = unique(self.tabs.get(tab, []) + items)

        def ready(items, error):
            if generation != self.library_generation:
                return
            self.loading.discard(tab)
            if error:
                self.tab_errors[tab] = error
                if self.tab == tab and isinstance(self.service, WebSoundCloud) and error == "SoundCloud: HTTP 401":
                    self.open_login()
                    self.login_error = "Сессия SoundCloud истекла. Нажмите Enter, чтобы восстановить вход."
            elif tab == "recent":
                self.tabs[tab] = unique(self.tabs.get(tab, []) + items) if self.recorded else items
            elif tab == "likes":
                publish_favorites(items)
                self.favorite_complete = True
            elif progressive:
                add_page(items, "")
            else:
                self.tabs[tab] = items

        if tab == "likes" and not self.demo:
            self.submit("browse", ready, self.service.favorites,
                        lambda page: self.events.put((partial, page, "")))
        elif progressive:
            self.submit("browse", ready, self.service.browse_section, tab,
                        lambda page: self.events.put((add_page, page, "")))
        else:
            self.submit("browse", ready, self.service.section, tab)

    def switch(self, tab):
        self.end_search()
        self.browse_version += 1
        self.context, self.context_items, self.stack = None, [], []
        self.selected = self.top = 0
        self.tab, self.error = tab, ""
        self.load_tab(tab)

    def open_collection(self, item):
        self.end_search()
        self.stack.append((self.context, self.context_items, self.selected, self.top))
        self.context, self.context_items = item, []
        self.selected = self.top = 0
        self.browse_version += 1
        version = self.browse_version
        self.notice, self.error = "Загрузка коллекции…", ""

        def ready(items, error):
            if version == self.browse_version:
                self.context_items = items or []
                self.notice, self.error = "", error

        self.submit("browse", ready, self.service.collection, item)

    def back(self):
        if self.searching:
            self.end_search()
        elif self.stack:
            self.browse_version += 1
            self.context, self.context_items, self.selected, self.top = self.stack.pop()
            self.notice, self.error = "", ""

    def base_items(self):
        return self.context_items if self.context else self.tabs.get(self.tab, [])

    def items(self):
        if not self.searching:
            return self.base_items()
        if self.global_search:
            return self.search_results
        return matches(self.base_items(), self.query)

    def begin_search(self, globally=False):
        globally = globally or (not self.context and self.tab not in ("likes", "playlists", "uploads"))
        if not self.searching:
            self.normal_selection = (self.selected, self.top)
        if not self.searching or globally != self.global_search:
            self.query = ""
        self.global_search = globally
        self.searching = self.editing = True
        self.full = False
        self.change_query()

    def end_search(self):
        if self.searching:
            self.selected, self.top = self.normal_selection
        self.searching = self.editing = False
        self.search_version += 1
        self.search_due = 0
        self.query = ""
        self.notice = ""

    def change_query(self):
        self.search_version += 1
        self.selected = self.top = 0
        self.search_due = 0
        self.error = ""
        if self.global_search:
            query = self.query.strip()
            self.search_results = matches(unique([item for items in self.tabs.values()
                                                  for item in items]), query) if query else []
            if query in self.search_cache:
                self.search_results = unique(self.search_results + self.search_cache[query])
                self.search_cache.move_to_end(query)
            elif query:
                self.search_due = time.monotonic() + .2

    def dispatch_search(self):
        self.search_due = 0
        query, version = self.query.strip(), self.search_version
        for future in self.search_futures:
            future.cancel()
        self.search_futures = [future for future in self.search_futures if not future.done()]
        self.notice = "Поиск в SoundCloud…"

        def ready(items, error):
            if not error:
                self.search_cache[query] = items
                while len(self.search_cache) > 24:
                    self.search_cache.popitem(last=False)
            if self.searching and self.global_search and version == self.search_version:
                self.search_results = unique(self.search_results + (items or []))
                self.notice, self.error = "", error

        self.search_futures.append(self.submit("search", ready, self.service.search, query))

    def prepare_art(self, url):
        if not url or url in self.cover_loading:
            return
        if url in self.covers:
            self.covers.move_to_end(url)
            return
        if len(self.cover_loading) >= 18:
            return
        self.cover_loading.add(url)

        def ready(data, error):
            self.cover_loading.discard(url)
            self.covers[url] = data or b""
            rows = self.screen.getmaxyx()[0] if self.screen is not None else 24
            while len(self.covers) > max(72, rows + 24):
                self.covers.popitem(last=False)

        if self.demo:
            self.submit("art", ready, demo_pixels, int(url.split(":")[1]))
        else:
            self.submit("art", ready, pixels, url)

    def stop_player(self):
        if self.player:
            self.player.close()
            self.retiring = self.player if isinstance(self.player, Playback) else None
        self.player = None

    def choose(self, track, queue, paused=False, offset=0):
        self.stop_player()
        if self.stream_future:
            self.stream_future.cancel()
        self.play_version += 1
        version = self.play_version
        self.track, self.queue = track, queue[:]
        if self.demo or self.service.signed_in:
            self.load_tab("likes")
        self.queue_index = next((i for i, item in enumerate(queue) if item.key == track.key), 0)
        self.position, self.want_pause = offset, paused
        self.pending_position = None
        self.dragging = False
        self.stream_url, self.preview = "", False
        self.stream_valid_until = 0
        self.play_status = self.play_error = ""
        self.timeline = Timeline()
        self.timeline.reset(offset)
        self.comment_status = "" if self.demo else "Загружаю комментарии…"
        self.wave_cancel.set()
        if self.wave_task:
            self.wave_task.cancel()
        self.wave_cancel = Event()
        self.wave_task = None
        self.samples = self.wave_cache.get(track.key, [])
        self.wave_ready = bool(self.samples)
        self.prepare_art(track.art)
        self.notice, self.error = "", ""
        if self.demo:
            self.timeline.set_comments(self.service.comments(track))
            self.samples = self.service.waveform(track)
            self.player = DemoPlayback(offset, track.duration, paused)
        else:
            def comments_ready(comments, error):
                if version == self.play_version:
                    self.comment_status = f"Комментарии: {error}" if error else ""
                    if not error:
                        self.timeline.set_comments(comments)

            def waveform_ready(samples, error):
                if version == self.play_version:
                    self.wave_ready = True
                    self.store_waveform(track, samples)
                    self.fallback_waveform()

            self.submit("meta", comments_ready, self.service.comments, track)
            if not self.wave_ready:
                self.submit("meta", waveform_ready, waveform, track)
            if not paused or self.service.signed_in:
                self.resolve_stream(prefetch=paused)

    def store_waveform(self, track, samples):
        if samples:
            self.samples = samples
            self.wave_cache[track.key] = samples
            self.wave_cache.move_to_end(track.key)
            while len(self.wave_cache) > 32:
                self.wave_cache.popitem(last=False)

    def fallback_waveform(self):
        if (not self.wave_ready or self.samples or self.wave_task or self.preview
                or not self.stream_url or not self.player or self.player.label != "Играет"):
            return
        version, track = self.play_version, self.track

        def ready(samples, error):
            if version == self.play_version:
                self.store_waveform(track, samples)

        self.wave_task = self.submit("wave", ready, decoded_waveform,
                                     self.stream_url, track.duration, self.wave_cancel)

    def resolve_stream(self, prefetch=False):
        track, version = self.track, self.play_version
        self.play_status = "" if prefetch else "Получаю аудиопоток…"
        self.play_error = ""

        def ready(result, error):
            if version != self.play_version:
                return
            self.play_status = ""
            if error:
                if not prefetch or not self.want_pause:
                    self.play_error = f"Не удалось запустить трек: {error}. Нажмите Играть для повтора."
                    self.want_pause = True
                return
            self.stream_url, self.preview = result
            self.stream_valid_until = time.monotonic() + 120
            if not self.want_pause:
                self.start_player(self.position)

        self.stream_future = self.submit("stream", ready, self.service.stream, track)

    def start_player(self, offset):
        self.stop_player()
        self.position = offset
        self.play_error = ""
        self.timeline.reset(offset)
        if self.demo:
            self.player = DemoPlayback(offset, self.track.duration, self.want_pause)
        elif self.stream_url:
            self.player = Playback(self.stream_url, offset, self.want_pause, self.gain(), self.retiring)

    def activate(self, index):
        items = self.items()
        if not 0 <= index < len(items):
            return
        item = items[index]
        self.selected = index
        if item.kind != "track":
            self.open_collection(item)
            return
        source = items if self.global_search and self.searching else self.base_items()
        self.original_queue = unique([track for track in source if track.kind == "track"])
        queue = self.original_queue[:]
        if self.shuffle:
            queue.remove(item)
            random.shuffle(queue)
            queue.insert(0, item)
        self.choose(item, queue)

    def queue_index_at(self, offset, automatic=False):
        if not self.queue:
            return None
        if automatic and self.repeat == "one":
            return self.queue_index
        index = self.queue_index + offset
        if self.repeat == "all":
            return index % len(self.queue)
        return index if 0 <= index < len(self.queue) else None

    def step(self, offset, automatic=False):
        index = self.queue_index_at(offset, automatic)
        if index is not None:
            self.choose(self.queue[index], self.queue)
            return True
        return False

    def toggle_shuffle(self):
        if not self.track or not self.queue:
            return
        self.shuffle = not self.shuffle
        if self.shuffle:
            tail = self.queue[self.queue_index + 1:]
            random.shuffle(tail)
            self.queue = self.queue[:self.queue_index + 1] + tail
        elif self.original_queue:
            self.queue = self.original_queue[:]
            self.queue_index = next(index for index, item in enumerate(self.queue) if item.key == self.track.key)

    def cycle_repeat(self):
        modes = {"off": "all", "all": "one", "one": "off"}
        self.repeat = modes[self.repeat]

    def toggle(self):
        if not self.track:
            return
        if isinstance(self.player, DemoPlayback):
            self.want_pause = not self.want_pause
            self.player.toggle()
        elif self.player and not self.player.stop.is_set():
            self.want_pause = not self.want_pause
            self.player.paused = self.want_pause
        elif self.stream_future and not self.stream_future.done():
            self.want_pause = not self.want_pause
            self.play_status = "" if self.want_pause else "Получаю аудиопоток…"
        else:
            self.want_pause = False
            if self.stream_url and time.monotonic() < self.stream_valid_until:
                self.start_player(self.position if self.position < self.track.duration else 0)
            else:
                self.resolve_stream()

    def gain(self):
        return 0 if self.muted else self.volume / 100

    def volume_change(self, delta=None):
        if delta is None:
            self.muted = not self.muted
        else:
            self.volume = max(0, min(100, self.volume + delta))
            self.muted = False
        if self.player:
            self.player.gain = self.gain()

    def favorite_button(self):
        key = numeric(self.track.key)
        if key in self.favorite_pending:
            return "[F Сохраняю…]", False
        if self.favorite_keys is not None and key in self.favorite_keys:
            return "[F В избранном]", True
        if self.favorite_complete:
            return "[F В избранное]", False
        label = "[F Проверяю…]" if "likes" in self.loading else "[F Проверить]"
        return label, False

    def like(self):
        if not self.track:
            return
        track = self.track
        key = numeric(track.key)
        if "likes" in self.loading:
            return
        if not self.favorite_complete and key not in (self.favorite_keys or ()):
            self.load_tab("likes")
            return
        if key in self.favorite_pending:
            return
        value = key not in self.favorite_keys
        generation = self.library_generation
        self.favorite_pending.add(key)

        def ready(_, error):
            if generation != self.library_generation:
                return
            self.favorite_pending.discard(key)
            self.error = error
            if not error:
                likes = [item for item in self.tabs["likes"] if numeric(item.key) != key]
                self.tabs["likes"] = [track] + likes if value else likes
                if value:
                    self.favorite_keys.add(key)
                else:
                    self.favorite_keys.discard(key)

        self.submit("browse", ready, self.service.like, track, value)

    def save(self):
        if not self.demo:
            state.write("session.json", {
                "volume": self.volume, "order": self.order, "right_art": self.right_art,
                "spectrum": self.show_spectrum, "tab": self.tab, "position": self.position,
                "track": asdict(self.track) if self.track else None,
                "context": asdict(self.context) if self.context else None,
                "queue": [asdict(track) for track in self.queue],
                "original_queue": [asdict(track) for track in self.original_queue],
                "shuffle": self.shuffle, "repeat": self.repeat,
            })

    def tick(self):
        while True:
            try:
                callback, result, error = self.events.get_nowait()
            except Empty:
                break
            callback(result, error)
        if self.search_due and time.monotonic() >= self.search_due:
            self.dispatch_search()
        player = self.player
        playing = player and not player.paused and player.label in ("Играет", "Демо · без звука")
        if player:
            self.position = player.position
            if playing:
                self.fallback_waveform()
            if not self.demo and player.stop.is_set() and not player.ended:
                self.stream_valid_until = 0
                self.want_pause = True
                self.play_error = f"Аудио не запустилось: {player.label}. Нажмите Играть для повтора."
            if playing and self.play_version != self.recorded:
                self.recorded = self.play_version
                self.tabs["recent"] = unique([self.track] + self.tabs.get("recent", []))[:25]
                if self.track.artist_key:
                    artist = Entry("user", self.track.artist_key, self.track.artist, art=self.track.art)
                    self.tabs["artists"] = unique([artist] + self.tabs.get("artists", []))[:25]
            if player.ended:
                self.want_pause = True
                if not self.step(1, automatic=True):
                    self.stop_player()
        self.active_comments = self.timeline.advance(self.position, playing and not self.dragging)
        levels = player.levels if playing else []
        for i in range(len(self.levels)):
            target = levels[i] if i < len(levels) else 0
            self.levels[i] += (target - self.levels[i]) * (.62 if target > self.levels[i] else .26)

    def put(self, y, x, value, style=0, limit=None):
        h, w = self.screen.getmaxyx()
        if not 0 <= y < h or not 0 <= x < w:
            return 0
        space = w - x - int(y == h - 1)
        if limit is not None:
            space = min(space, limit)
        result = []
        width = 0
        for char in clean(value):
            size = cell_width(char)
            if width + size > space:
                break
            result.append(char)
            width += size
        try:
            if result:
                self.screen.addstr(y, x, "".join(result), style)
        except curses.error:
            pass
        return width

    def color(self, index, extra=0):
        return (curses.color_pair(index) if curses.has_colors() else 0) | extra

    def rgb(self, color):
        if not curses.has_colors() or curses.COLORS < 256 or curses.COLOR_PAIRS < 256:
            return self.color(ORANGE)
        value = 16 + 36 * round(color[0] / 51) + 6 * round(color[1] / 51) + round(color[2] / 51)
        if value not in self.colors:
            pair = len(self.colors) + 20
            curses.init_pair(pair, value, self.background)
            self.colors[value] = pair
        return self.color(self.colors[value])

    def frame(self, y, x, w, h, title):
        if h < 2 or w < 3:
            return
        tl, tr, bl, br, hz, vt = "+", "+", "+", "+", "-", "|"
        if not self.ascii:
            tl, tr, bl, br, hz, vt = "╭╮╰╯─│"
        style = self.color(DIM)
        self.put(y, x, tl + hz * (w - 2) + tr, style)
        self.put(y + h - 1, x, bl + hz * (w - 2) + br, style)
        for row in range(y + 1, y + h - 1):
            self.put(row, x, vt, style)
            self.put(row, x + w - 1, vt, style)
        self.put(y, x + 2, f" {title} ", self.color(ORANGE, curses.A_BOLD), w - 4)

    def button(self, y, x, text, action, active=False, limit=None):
        width = self.put(y, x, text, self.color(ORANGE if active else WHITE,
                                                curses.A_BOLD if active else 0), limit)
        if width:
            self.hits.append((y, x, x + width, action))
        return x + width + 2

    def cover(self, url, y, x, w, h, crop=False):
        data = self.covers.get(url)
        if not data:
            self.prepare_art(url)
            return
        self.covers.move_to_end(url)
        for row, values in enumerate(dots(data, w, h, self.ascii, crop)):
            for col, (glyph, color) in enumerate(values):
                self.put(y + row, x + col, glyph, self.rgb(color))

    def render_search(self, w):
        if self.searching and self.global_search:
            scope = "Весь SoundCloud"
        elif self.context:
            scope = SCOPES[self.context.kind]
        else:
            scope = {"likes": "В любимых треках", "playlists": "В плейлистах",
                     "uploads": "В моих треках"}.get(self.tab, "Весь SoundCloud")
        self.frame(0, 0, w, 3, f"tsound  /  {scope}")
        x = self.button(1, 2, "[F2 Весь SoundCloud]", lambda: self.begin_search(True))
        self.button(1, x, f"/ {self.query}" + ("_" if self.editing else ""),
                    self.focus_search, self.editing, w - x - 2)
        self.hits.append((1, x, w - 1, self.focus_search))

    def focus_search(self):
        if self.searching:
            self.editing = True
        else:
            self.begin_search()

    def render_list(self, y, w, h):
        title = "Список" if self.searching else self.context.title if self.context else "Библиотека"
        self.frame(y, 0, w, h, title)
        x = 2
        row = y + 1
        if self.library_view or (not self.context and not self.searching):
            for i, (tab, label) in enumerate(TABS.items(), 1):
                text = f"{i} {label}"
                if x + len(text) > w - 1:
                    x, row = 2, row + 1
                if row >= y + h - 1:
                    break
                x = self.button(row, x, text, lambda tab=tab: self.switch(tab), self.tab == tab)
            row += 1
        if self.context:
            self.button(row, 2, "[Назад]", self.back)
            row += 1
        self.page = max(1, y + h - row - 1)
        if row >= y + h - 1:
            return
        if self.tab == "apps" and not self.searching:
            self.put(row, 3, "tsound 0.1 · Python / curses · FFmpeg / SDL2")
            if row + 1 < y + h - 1:
                self.button(row + 1, 3, "[F5 Войти в SoundCloud]", self.open_login)
            return
        items = self.items()
        if not items:
            if not self.searching and not self.context and self.tab in self.tab_errors:
                self.button(row, 3, f"[Обновить] {self.tab_errors[self.tab]}",
                            lambda: self.load_tab(self.tab, refresh=True), limit=w - 5)
                return
            if self.searching:
                message = "Начните вводить запрос" if not self.query else "Совпадений пока нет"
            elif self.tab in self.loading:
                message = "Загрузка…"
            else:
                message = "Список пуст"
            self.put(row, 3, message, self.color(DIM), w - 5)
            return
        self.selected = min(self.selected, len(items) - 1)
        self.top = max(0, min(self.top, self.selected))
        if self.selected >= self.top + self.page:
            self.top = self.selected - self.page + 1
        for index, item in enumerate(items[self.top:self.top + self.page], self.top):
            active = index == self.selected
            self.put(row, 2, ">" if active else " ", self.color(ORANGE))
            self.cover(item.art, row, 4, 2, 1)
            detail = " · ".join(filter(None, (item.artist, item.release, KINDS.get(item.kind))))
            suffix = clock(item.duration) if item.duration else ""
            edge = w - 3 - len(suffix)
            title_width = min(max(12, w // 2), max(0, edge - 8)) if detail else max(0, edge - 8)
            used = self.put(row, 7, item.title, self.color(WHITE, curses.A_BOLD if active else 0), title_width)
            if detail:
                self.put(row, 9 + used, detail, self.color(DIM), edge - 10 - used)
            self.put(row, edge, suffix, self.color(GREEN))
            self.hits.append((row, 2, w - 1, lambda index=index: self.activate(index)))
            row += 1
        for item in items[max(0, self.top - 2):self.top + self.page + 2]:
            self.prepare_art(item.art)

    def open_source(self):
        if self.track:
            target = urlsplit(self.track.permalink)
            if target.scheme == "https" and target.netloc in ("soundcloud.com", "www.soundcloud.com"):
                self.submit("browse", lambda result, error: None, webbrowser.open,
                            self.track.permalink)

    def share(self):
        if not self.track:
            return
        url = self.track.permalink
        target = urlsplit(url)
        if target.scheme != "https" or target.netloc not in ("soundcloud.com", "www.soundcloud.com"):
            self.notice = "Для этого трека нет ссылки SoundCloud."
            return
        commands = (("wl-copy",), ("xclip", "-selection", "clipboard"), ("xsel", "--clipboard", "--input"))
        options = next((command for command in commands if shutil.which(command[0])), None)
        if options is None:
            self.notice = f"Поделиться: {url}"
            return

        def copy():
            return subprocess.run(options, input=url, text=True, timeout=3,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

        def ready(copied, error):
            self.notice = "Ссылка скопирована." if copied and not error else f"Поделиться: {url}"

        self.submit("meta", ready, copy)

    def render_player(self, y, w, h, landscape=False):
        self.frame(y, 0, w, h, "Сейчас играет")
        if not self.track:
            if h > 2:
                self.put(y + 1, 2, "Выберите трек", self.color(DIM))
            return
        track = self.track
        if landscape:
            art_h = h - 2
            art_w = (w - 8) * 47 // 100
            art_y, art_x = y + 1, 2
            x = art_x + art_w + 3
            available = w - x - 2
            wave_y, wave_space = y + 4, h
        elif self.full:
            art_h = min((w - 4) // 2, max(0, (h - 14) * 2 // 3))
            art_w = min(w - 4, round(art_h * 2.1))
            art_y, art_x = y + 3, (w - art_w) // 2
            x, available = 2, w - 4
            wave_y = art_y + art_h + 1
            wave_space = h - art_h
        else:
            art_w = min(2 * w // 5, 2 * (h - 2)) if h >= 9 and w >= 62 else 0
            art_h = min(h - 2, max(1, round(art_w / 2.1)))
            art_y, art_x = y + 1, w - art_w - 2 if self.right_art else 2
            x = 2 if self.right_art or not art_w else art_w + 4
            available = w - art_w - (6 if art_w else 4)
            wave_y, wave_space = y + 3, h
        if art_w:
            self.cover(track.art, art_y, art_x, art_w, art_h, crop=landscape)
            for cover_row in range(art_y, art_y + art_h):
                self.hits.append((cover_row, art_x, art_x + art_w, self.toggle_full))
        if h < 5:
            self.put(y + 1, x, f"{track.title} · {track.artist} · {clock(self.position)}", self.color(WHITE), available)
            return
        self.put(y + 1, x, track.title, self.color(WHITE, curses.A_BOLD), available)
        self.put(y + 2, x, " · ".join(filter(None, (track.artist, track.release))),
                 self.color(DIM), available)
        if h < 9:
            self.put(y + 3, x, clock(self.position) + " / " + clock(track.duration), self.color(GREEN))
            return
        position = self.pending_position if self.pending_position is not None else self.position
        width = available
        spectrum_h = min(8, max(3, (h - 13) // 4)) if landscape and self.show_spectrum else 0
        reserve = (14 + spectrum_h if spectrum_h else 12) if landscape else (
            14 if self.full else 10 if available < 49 else 9)
        height = max(1, (wave_space - reserve) // 2)
        if not landscape:
            height = min(10 if self.full else 7, height)
        axis = wave_y + height
        playhead = column(position, track.duration, width)
        marks = {}
        for comment in self.timeline.comments:
            if comment.seconds <= track.duration:
                marks.setdefault(column(comment.seconds, track.duration, width), []).append(comment)
        hovered = None
        if self.mouse_position and not self.dragging:
            mouse_x, mouse_y = self.mouse_position
            if abs(mouse_y - axis) <= 1 and mouse_x - x in marks:
                hovered = mouse_x - x
        amplitude = peaks(self.samples, width)
        bar = "|" if self.ascii else "┃"
        dot = "*" if self.ascii else "•"
        for index in range(width):
            played = index < playhead
            head = index == playhead
            style = self.color(ORANGE if played or head else DIM)
            ticks = round(amplitude[index] * height * 8) if amplitude else 0
            for level in range(1, height + 1):
                fill = ticks - (level - 1) * 8
                if fill <= 0 and not head:
                    break
                if played:
                    top_glyph = bottom_glyph = dot
                elif head or fill >= 5 or self.ascii:
                    top_glyph = bottom_glyph = bar
                else:
                    top_glyph, bottom_glyph = "╹", "╻"
                self.put(axis - level, x + index, top_glyph, style)
                self.put(axis + level, x + index, bottom_glyph,
                         style)
            if index in marks:
                glyph = ("O" if self.ascii else "◉") if index == hovered else ("o" if self.ascii else "●")
                style = self.color(GREEN, curses.A_REVERSE if index == hovered else curses.A_BOLD)
            elif head:
                glyph = bar
            elif played:
                glyph = dot
            else:
                glyph = "-" if self.ascii else "─"
            self.put(axis, x + index, glyph, style)
        self.wave_hit = (x, width, axis - height, axis + height)
        row = axis + height + (2 if self.full else 1)
        transport_row = row + (2 if self.full else 1)
        modes_row = transport_row + 2
        next_row = modes_row + 1
        total = clock(track.duration) if track.duration else "—"
        subtitle = f"{clock(position)} / {total}"
        if self.preview:
            subtitle += " · фрагмент"
        elif not amplitude:
            pending = not self.wave_ready or (self.wave_task and not self.wave_task.done())
            subtitle += " · загрузка формы волны…" if pending else " · форма волны недоступна"
        used = self.put(row, x, subtitle, self.color(GREEN), available)
        button_x = x + used + 2
        for label, action in (
            ("[F3 Свернуть]" if self.full else "[F3 Развернуть]", self.toggle_full),
            ("[o SoundCloud]", self.open_source) if track.permalink else ("", None),
        ):
            if action and button_x + len(label) <= x + available:
                button_x = self.button(row, button_x, label, action)
        favorite_drawn = self.render_transport(transport_row, x, available)
        if transport_row + 1 < y + h - 1:
            if not favorite_drawn:
                label, liked = self.favorite_button()
                self.button(transport_row + 1, x, label, self.like, liked, available)
            elif self.comment_status:
                self.put(transport_row + 1, x, self.comment_status, self.color(DIM), available)

        if modes_row < y + h - 1:
            repeat = {"off": "выкл", "all": "все", "one": "трек"}[self.repeat]
            shuffle_label = "Перемешать" if available >= 58 else "Микс"
            buttons = (
                (f"[S {shuffle_label}: {'вкл' if self.shuffle else 'выкл'}]", self.toggle_shuffle, self.shuffle),
                (f"[R Повтор: {repeat}]", self.cycle_repeat, self.repeat != "off"),
                ("[Y Поделиться]", self.share, False),
            )
            cursor = x
            for label, action, active in buttons:
                if cursor + len(label) > x + available:
                    break
                cursor = self.button(modes_row, cursor, label, action, active)
        if self.full and next_row < y + h - 1:
            index = self.queue_index_at(1, automatic=True)
            next_track = self.queue[index] if index is not None else None
            label = f"Далее: {next_track.title} · {next_track.artist}" if next_track else "Далее: конец очереди"
            self.put(next_row, x, label, self.color(DIM), available)
        if spectrum_h:
            spectrum_y = y + h - 1 - spectrum_h
            if spectrum_y > next_row:
                self.render_spectrum(spectrum_y, available, spectrum_h, x=x)

        comments = marks[hovered] if hovered is not None else self.active_comments[::-1]
        if comments and not self.dragging:
            comment = comments[0]
            anchor = column(comment.seconds, track.duration, width)
            bubble_width = min(available, 68)
            left = x + max(0, min(anchor - 2, available - bubble_width))
            text = clean(f"{clock(comment.seconds)}  @{comment.author}  {comment.body}")
            lines = wrap(text, width=max(1, bubble_width - 2), max_lines=min(3, height),
                         placeholder=" …")
            for offset, line in enumerate(lines, 1):
                self.put(axis + offset, left, (" " + line).ljust(bubble_width),
                         self.color(ORANGE, curses.A_REVERSE | curses.A_BOLD), bubble_width)
            self.comment_drawn = True

    def render_transport(self, y, x, width):
        wide = width >= 62
        controls = [
            ("[Пауза]" if self.player and not self.player.paused and
             not self.player.ended else "[Играть]", self.toggle),
            ("[← Назад]" if wide else "[←]", lambda: self.step(-1)),
            ("[Вперёд →]" if wide else "[→]", lambda: self.step(1)),
            ("[-]", lambda: self.volume_change(-5)),
            ("[Muted]" if self.muted else f"[{self.volume}%]", self.volume_change),
            ("[+]", lambda: self.volume_change(5)),
        ]
        right = x + width
        for index, (label, action) in enumerate(controls):
            if x + len(label) > right:
                break
            x = self.button(y, x, label, action, index == 0) - 1
        self.transport_drawn = True
        label, liked = self.favorite_button()
        if x + len(label) <= right:
            self.button(y, x, label, self.like, liked)
            return True
        return False

    def render_mini_player(self, y, w, h):
        self.frame(y, 0, w, h, "Сейчас играет")
        if not self.track:
            self.put(y + 1, 2, "Выберите трек", self.color(DIM))
            return
        self.cover(self.track.art, y + 1, 2, 4, 2)
        size = min(30, w // 3)
        ramp = " .:-=+*#@" if self.ascii else " ▁▂▃▄▅▆▇█"
        spectrum = "".join(ramp[round(self.levels[i * len(self.levels) // size] * 8)]
                           for i in range(size))
        self.put(y + 1, 8, self.track.title, self.color(WHITE, curses.A_BOLD), w - size - 12)
        progress = f"{clock(self.position)} / {clock(self.track.duration)}"
        self.put(y + 2, 8, progress, self.color(GREEN), w - size - 12)
        if self.show_spectrum:
            self.put(y + 2, w - size - 2, spectrum, self.color(ORANGE))

    def render_spectrum(self, y, w, h, x=0):
        self.frame(y, x, w, h, "Спектр")
        for col in range(2, w - 2):
            index = (col - 2) * len(self.levels) // (w - 4)
            for row in range(round(self.levels[index] * (h - 2))):
                self.put(y + h - 2 - row, x + col, "." if self.ascii else "⠿", self.color(ORANGE))

    def render_footer(self, y, w):
        actions = [
            ("[F4 Плеер]" if self.library_view else "[F4 Библиотека]", self.toggle_library),
            ("[F5 Вход]", self.open_login), ("[F1 ?]", self.toggle_help),
        ]
        x = 1
        if self.track and not self.transport_drawn:
            self.render_transport(y, 1, min(w - 17, 48))
            x = min(w - 17, 48) + 2
        for label, action in actions:
            if x + len(label) >= w - 1:
                break
            x = self.button(y, x, label, action)
        label = self.player.label if self.player else ("Пауза" if self.track else "")
        library_error = "" if self.context or self.searching else self.tab_errors.get(self.tab, "")
        status = self.play_error or self.play_status or self.error or self.notice or library_error or label
        comment = self.footer_comment or (self.active_comments[-1] if self.active_comments else None)
        if comment and not self.comment_drawn and (self.footer_comment or not (self.error or self.notice or self.play_error or self.play_status)):
            status = f"@{comment.author}  {comment.body}"
        self.put(y + 1, 1, status, self.color(ERROR if self.error or self.play_error or library_error else DIM))

    def render_overlay(self, w, h):
        lines = ([
            "↑↓ Выбор   Enter Открыть / играть   Backspace Назад",
            "/ Поиск в разделе   F2 Весь SoundCloud   Esc Выйти из поиска",
            "F3 Большой плеер   F4 / B Библиотека   F5 Вход",
            "Наведите на точку для комментария. Перетащите плейхед для перемотки.",
            "F7 / p Назад   F8 / Space Пауза   F9 / n Далее",
            "F10 / m Mute   F11 / - Тише   F12 / + Громче",
            "S Перемешать   R Повтор   Y Поделиться",
            "f Избранное   L Раскладка   1–8 Разделы   Ctrl+Q Выход",
        ] if self.help else [
            f"↑↓ Порядок панелей: {self.order + 1} / {len(ORDERS)}",
            f"A Обложка: {'справа' if self.right_art else 'слева'}",
            f"S Спектр: {'включён' if self.show_spectrum else 'выключен'}",
            "Enter или Esc — вернуться",
        ])
        self.frame(3, 0, w, h - 5, "Справка" if self.help else "Настройка раскладки")
        for i, line in enumerate(lines):
            if 4 + i < h - 3:
                self.put(4 + i, 2, line, self.color(WHITE), w - 4)

    def open_login(self):
        if self.demo:
            self.notice = "Для входа запустите tsoundcloud без --demo"
            return
        self.login = True
        self.login_error = self.login_status = ""

    def close_login(self):
        if self.login_attempt:
            self.login_attempt.set()
            self.login_attempt = None
        self.login = False
        self.load_tab(self.tab)

    def send_login(self, separate=False):
        if self.login_attempt:
            return
        attempt = self.login_attempt = Event()
        self.login_error = self.login_status = ""
        def complete(_, error):
            if self.login_attempt is not attempt:
                return
            self.login_attempt = None
            self.login_error = error
            if not error:
                self.library_generation += 1
                self.tabs.clear()
                self.tab_errors.clear()
                self.loading.clear()
                self.favorite_keys = None
                self.favorite_complete = False
                self.favorite_pending.clear()
                self.close_login()
                if self.track:
                    self.load_tab("likes")
                self.notice, self.error = "Вход выполнен", ""

        if isinstance(self.service, WebSoundCloud) and not separate:
            self.login_status = "Проверяю сессию SoundCloud в браузере…"

            def status(opened, error):
                if self.login_attempt is attempt:
                    self.login_status = ("Ожидаю вход. Если окно не появилось, откройте ссылку выше в рабочем Zen."
                                         if opened else
                                         "Браузер не открылся. Откройте ссылку выше в рабочем Zen. Терминал ждёт вход.")

            self.submit("browse", complete, self.service.default_browser_login, attempt,
                        lambda opened: self.events.put((status, opened, "")))
        else:
            self.submit("browse", complete, self.service.browser_login, attempt)

    def render_login(self, w, h):
        self.frame(1, 0, w, h - 2, "Вход в SoundCloud")
        if not self.login_attempt:
            self.button(3, 2, "[Enter Войти в SoundCloud]" if isinstance(self.service, WebSoundCloud)
                        else "[Enter Войти через браузер]", self.send_login, True)
            if isinstance(self.service, WebSoundCloud):
                self.put(4, 2, "Использовать и запомнить сессию из обычного браузера.",
                         self.color(DIM), w - 4)
                self.button(6, 2, "[S Войти в отдельном профиле]", lambda: self.send_login(separate=True))
        self.button(8, 2, "[Esc Закрыть]", self.close_login)
        if isinstance(self.service, WebSoundCloud) and self.login_attempt and self.login_status:
            self.put(6, 2, "https://soundcloud.com/signin", self.color(ORANGE), w - 4)
        status = self.login_error or self.login_status
        if self.login_attempt and not status:
            status = "Войдите на сайте SoundCloud. Терминал откроет библиотеку после входа."
        for row, line in enumerate(wrap(status, width=w - 4), 10):
            self.put(row, 2, line, self.color(ERROR if self.login_error else DIM), w - 4)

    def login_input(self, key):
        if key == "\x1b" or key == curses.KEY_F5:
            self.close_login()
        elif key == curses.KEY_F4:
            self.close_login()
            self.toggle_library()
        elif key in ("\n", "\r", curses.KEY_ENTER):
            self.send_login()
        elif key in ("s", "S") and isinstance(self.service, WebSoundCloud):
            self.send_login(separate=True)

    def render_splash(self, w, h):
        logo = (
            "                   ....",
            "              .:::::::::.",
            "            .::::::::::::::.",
            "      .    ::::::::::::::::::.",
            "   .  :  : ::::::::::::::::::::.",
            " . :  :  : :::::::::::::::::::::",
            " : :  :  : ::::::::::::::::::::.",
            " . .  :  : ::::::::::::::::::.'",
        )
        wide = w >= 72
        x = max(1, (w - (68 if wide else 32)) // 2)
        y = max(0, (h - (8 if wide else 10)) // 2)
        accent = self.color(ORANGE, curses.A_BOLD)
        for row, line in enumerate(logo):
            self.put(y + row, x, line, accent)
        if not wide:
            self.put(y + 9, x, "       SoundCloud Terminal", accent)
            return
        info = (
            ("SoundCloud Terminal", "  v0.1.0"),
            ("-------------------", ""),
            ("Система", f"  {platform.system()} {platform.machine()}"),
            ("Режим", "  Беззвучное демо" if self.demo else "  SoundCloud"),
            ("Терминал", f"  {os.getenv('TERM', 'curses')}"),
        )
        for row, (label, value) in enumerate(info):
            used = self.put(y + row + 1, x + 36, label, accent)
            self.put(y + row + 1, x + 36 + used, value, self.color(WHITE))

    def draw(self):
        self.screen.erase()
        self.hits, self.wave_hit = [], None
        self.comment_drawn = False
        self.footer_comment = None
        self.transport_drawn = False
        h, w = self.screen.getmaxyx()
        if self.splash > time.monotonic() and h >= 10 and w >= 32:
            self.render_splash(w, h)
        elif h < 16 or w < 36:
            self.put(0, 0, "Увеличьте терминал до 36 × 16")
        elif self.login:
            self.render_login(w, h)
        else:
            self.render_search(w)
            if self.help or self.layout:
                self.render_overlay(w, h)
            else:
                remaining = h - 5
                spectrum_h = (4 if h < 31 else 5) if self.show_spectrum and h >= 23 else 0
                landscape = self.full and h >= 22 and w >= max(88, 5 * h // 2)
                if landscape:
                    order = ("landscape",)
                    heights = {"landscape": remaining}
                elif self.full:
                    if spectrum_h:
                        spectrum_h = min(8, max(4, remaining // 10))
                    player_h = min(remaining - spectrum_h, (w - 4) // 2 + 30)
                    order = ("player", "spectrum")
                    heights = {"player": player_h, "spectrum": spectrum_h}
                elif self.library_view:
                    order = ("list", "mini")
                    heights = {"list": remaining - 4, "mini": 4}
                elif self.searching:
                    compact = 3 if h < 24 else 5
                    spectrum_h = 3 if spectrum_h and h >= 26 else 0
                    order = ("list", "player", "spectrum")
                    heights = {"player": compact, "spectrum": spectrum_h,
                               "list": remaining - compact - spectrum_h}
                else:
                    player_h = min(23, max(7, remaining * 3 // 5), max(3, remaining - spectrum_h - 6))
                    order = ORDERS[self.order]
                    heights = {"player": player_h, "spectrum": spectrum_h,
                               "list": remaining - player_h - spectrum_h}
                y = 3
                renderers = {"player": self.render_player, "spectrum": self.render_spectrum,
                             "landscape": lambda y, w, h: self.render_player(y, w, h, landscape=True),
                             "list": self.render_list, "mini": self.render_mini_player}
                for panel in order:
                    height = heights[panel]
                    if height:
                        renderers[panel](y, w, height)
                        y += height
            self.render_footer(h - 2, w)
        self.screen.refresh()

    def toggle_full(self):
        self.end_search()
        self.full = not self.full
        self.pending_position, self.dragging = None, False

    def toggle_library(self):
        self.full = self.help = self.layout = False
        self.library_view = not self.library_view
        self.pending_position, self.dragging = None, False

    def toggle_help(self):
        self.help = not self.help

    def move(self, amount):
        self.editing = False
        self.selected = max(0, min(len(self.items()) - 1, self.selected + amount))

    def seek_mouse(self, x, y, button):
        if not self.wave_hit or not self.track.duration or self.preview:
            return False
        start, width, top, bottom = self.wave_hit
        down = button & getattr(curses, "BUTTON1_PRESSED", 0)
        release = button & getattr(curses, "BUTTON1_RELEASED", 0)
        click = button & getattr(curses, "BUTTON1_CLICKED", 0)
        moving = button & getattr(curses, "REPORT_MOUSE_POSITION", 0)
        inside = start <= x < start + width and top <= y <= bottom
        if not self.dragging and not (inside and (down or click)):
            return False
        if down or click or release or moving:
            index = max(0, min(width - 1, x - start))
            self.pending_position = self.track.duration * index / max(1, width - 1)
        if release or click:
            offset = self.pending_position
            self.pending_position, self.dragging = None, False
            if offset is not None:
                self.position = offset
                self.timeline.reset(offset)
                if self.demo or self.stream_url:
                    self.start_player(offset)
        elif down:
            self.dragging = True
        return True

    def mouse(self):
        try:
            _, x, y, _, button = curses.getmouse()
        except curses.error:
            return
        self.mouse_position = (x, y)
        if self.seek_mouse(x, y, button):
            return
        if button & getattr(curses, "BUTTON4_PRESSED", 0):
            self.move(-3)
        elif button & getattr(curses, "BUTTON5_PRESSED", 0):
            self.move(3)
        elif button & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
            for row, start, end, action in self.hits:
                if y == row and start <= x < end:
                    action()
                    break

    def input(self, key):
        if key != curses.KEY_MOUSE:
            self.splash = 0
        if key == "\x0c":
            self.screen.clearok(True)
            return
        if key == "\x11":
            self.running = False
            return
        if key == curses.KEY_MOUSE:
            self.mouse()
            return
        if self.login:
            self.login_input(key)
            return
        if key == "\x1b":
            if self.help or self.layout or self.full:
                self.help = self.layout = self.full = False
            elif self.library_view and not self.searching:
                self.toggle_library()
            else:
                self.back()
            return
        fkeys = {curses.KEY_F1: self.toggle_help, curses.KEY_F2: lambda: self.begin_search(True),
                 curses.KEY_F3: self.toggle_full, curses.KEY_F4: self.toggle_library,
                 curses.KEY_F5: self.open_login,
                 curses.KEY_F7: lambda: self.step(-1),
                 curses.KEY_F8: self.toggle, curses.KEY_F9: lambda: self.step(1),
                 curses.KEY_F10: self.volume_change, curses.KEY_F11: lambda: self.volume_change(-5),
                 curses.KEY_F12: lambda: self.volume_change(5)}
        if key in fkeys:
            fkeys[key]()
            return
        if self.help:
            if key in ("?", "\n"):
                self.help = False
            return
        if self.layout:
            if key in (curses.KEY_UP, curses.KEY_DOWN):
                self.order = (self.order + (1 if key == curses.KEY_DOWN else -1)) % len(ORDERS)
            elif key in ("a", "A"):
                self.right_art = not self.right_art
            elif key in ("s", "S"):
                self.show_spectrum = not self.show_spectrum
            elif key in ("\n", "\r", "L"):
                self.layout = False
            return
        if self.editing:
            if key in ("\t", "\n", "\r", curses.KEY_DOWN, curses.KEY_ENTER):
                self.editing = False
            elif key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                self.query = self.query[:-1]
                self.change_query()
            elif key == "\x15":
                self.query = ""
                self.change_query()
            elif isinstance(key, str) and key.isprintable():
                self.query = (self.query + key)[:160]
                self.change_query()
            return
        actions = {
            "/": self.focus_search, " ": self.toggle, "p": lambda: self.step(-1),
            "n": lambda: self.step(1), "m": self.volume_change,
            "-": lambda: self.volume_change(-5), "+": lambda: self.volume_change(5),
            "f": self.like, "o": self.open_source,
            "s": self.toggle_shuffle, "S": self.toggle_shuffle, "r": self.cycle_repeat,
            "R": self.cycle_repeat, "y": self.share, "Y": self.share, "b": self.toggle_library, "B": self.toggle_library, "L": lambda: setattr(self, "layout", True), "?": self.toggle_help,
            curses.KEY_UP: lambda: self.move(-1), curses.KEY_DOWN: lambda: self.move(1),
            curses.KEY_PPAGE: lambda: self.move(-self.page),
            curses.KEY_NPAGE: lambda: self.move(self.page),
            curses.KEY_BACKSPACE: self.back, "\x7f": self.back, "\b": self.back,
        }
        if key in actions:
            actions[key]()
        elif key in ("\n", "\r", curses.KEY_ENTER) and not self.full:
            self.activate(self.selected)
        elif isinstance(key, str) and key in "12345678":
            self.switch(tuple(TABS)[int(key) - 1])

    def read_key(self):
        key = self.screen.get_wch()
        if key != "\x1b":
            return key
        tail = []
        self.screen.timeout(12)
        try:
            while len(tail) < 4:
                char = self.screen.get_wch()
                tail.append(char)
                if not isinstance(char, str):
                    break
                sequence = "".join(tail)
                if sequence in FUNCTION_ESC:
                    return FUNCTION_ESC[sequence]
                if not any(candidate.startswith(sequence) for candidate in FUNCTION_ESC):
                    break
        except curses.error:
            pass
        finally:
            self.screen.timeout(40)
        for char in reversed(tail):
            if isinstance(char, int):
                curses.ungetch(char)
            else:
                curses.unget_wch(char)
        return key

    def run(self):
        self.screen.keypad(True)
        self.screen.timeout(40)
        curses.raw()
        curses.set_escdelay(35)
        curses.noecho()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        curses.mousemask(curses.ALL_MOUSE_EVENTS | getattr(curses, "REPORT_MOUSE_POSITION", 0))
        curses.mouseinterval(0)
        if curses.has_colors():
            curses.start_color()
            self.background = 0
            try:
                curses.use_default_colors()
                self.background = -1
            except curses.error:
                pass
            for index, color in ((ORANGE, 208 if curses.COLORS >= 256 else curses.COLOR_YELLOW),
                                 (WHITE, curses.COLOR_WHITE),
                                 (DIM, 245 if curses.COLORS >= 256 else curses.COLOR_CYAN),
                                 (GREEN, curses.COLOR_GREEN), (ERROR, curses.COLOR_RED)):
                curses.init_pair(index, color, self.background)
        xterm_mouse = os.name != "nt" and os.getenv("TERM", "").startswith(
            ("xterm", "screen", "tmux", "foot", "alacritty", "kitty"))
        if xterm_mouse:
            print("\x1b[?1003h", end="", flush=True)
        try:
            while self.running:
                self.tick()
                self.draw()
                try:
                    key = self.read_key()
                except curses.error:
                    continue
                self.input(key)
        finally:
            if xterm_mouse:
                print("\x1b[?1003l", end="", flush=True)
            self.wave_cancel.set()
            if self.login_attempt:
                self.login_attempt.set()
            self.stop_player()
            if self.retiring:
                self.retiring.thread.join(timeout=2)
            for pool in self.pools.values():
                pool.shutdown(wait=False, cancel_futures=True)
            self.save()
