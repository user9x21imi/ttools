#!/usr/bin/env python3
"""Capture deterministic tspotify editorial UI screenshots, transitions and render timings."""

import argparse
import curses
import json
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tspotify import demo, ui  # noqa: E402


class FakeScreen:
    def __init__(self, height, width):
        self.size = height, width

    def getmaxyx(self):
        return self.size

    def addnstr(self, y, x, text, limit, style=0):
        if not (0 <= y < self.size[0] and 0 <= x < self.size[1]):
            raise AssertionError(f"out of bounds write at {(y, x)}")

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def install_headless_curses():
    curses.has_colors = lambda: True
    curses.color_pair = lambda pair: pair
    curses.start_color = lambda: None
    curses.use_default_colors = lambda: None
    curses.init_pair = lambda *args: None
    curses.curs_set = lambda *args: None
    curses.COLORS = 256
    curses.COLOR_PAIRS = 65536


def xterm_color(index):
    if index < 16:
        base = [
            (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
            (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
            (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
            (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
        ]
        return base[index]
    if index < 232:
        levels = (0, 95, 135, 175, 215, 255)
        value = index - 16
        return levels[value // 36], levels[(value // 6) % 6], levels[value % 6]
    grey = 8 + (index - 232) * 10
    return grey, grey, grey


def image_for(app, font_path, *, cell_width=11, cell_height=20):
    grid = app._display_grid or app._last_grid
    font = ImageFont.truetype(font_path, 16)
    base_pairs = {
        pair_id: (foreground, background)
        for key, pair_id in app.colors.items()
        if isinstance(key, tuple) and len(key) == 2 and all(isinstance(x, int) for x in key)
        for foreground, background in (key,)
    }
    dot_pairs = {
        pair_id: (key[1], -1)
        for key, pair_id in app.colors.items()
        if isinstance(key, tuple) and len(key) == 2 and key[0] == "dot"
    }
    base_pairs.update(dot_pairs)
    canvas = Image.new("RGB", (grid.width * cell_width, grid.height * cell_height), (15, 18, 17))
    draw = ImageDraw.Draw(canvas)
    for y, row in enumerate(grid.cells):
        for x, cell in enumerate(row):
            if cell.glyph == "":
                continue
            foreground, background = base_pairs.get(cell.color, (244, -1))
            x0, y0 = x * cell_width, y * cell_height
            if background >= 0:
                draw.rectangle(
                    (x0, y0, x0 + cell_width - 1, y0 + cell_height - 1),
                    fill=xterm_color(background),
                )
            if cell.glyph != " ":
                draw.text((x0, y0 + 1), cell.glyph, font=font, fill=xterm_color(foreground))
    return canvas


def close_app(app):
    for pool_name in (
        "search_pool", "state_pool", "transport_pool", "pool", "art_pool", "cover_pool"
    ):
        getattr(app, pool_name).shutdown(wait=True, cancel_futures=True)
    app.audio.close()


def ready_app(size):
    screen = FakeScreen(*size)
    app = ui.App(screen)
    deadline = time.monotonic() + 2
    while app.pending and time.monotonic() < deadline:
        app.drain()
        time.sleep(0.002)
    item = demo.Demo().tracks[0]
    item = {
        **item,
        "name": "Night Drive Through the City After Midnight",
        "artists": [{"name": "Ghosts on Tape"}],
        "album": {"id": "demo", "name": "After Hours / Signals at 2AM", "images": [{"url": "demo:cover"}]},
    }
    app.playback = {
        "item": item,
        "next_item": {"name": "Soft Signals", "artists": [{"name": "Moonlight Arcade"}]},
        "progress_ms": 87000,
        "is_playing": True,
        "device": {"name": "DEMO / no audio", "volume_percent": 35},
        "repeat_state": "off",
    }
    app.volume = app.volume_applied = 35
    app.updated = time.monotonic()
    app.art = demo.picture()
    app.art_url = "demo:cover"
    app.visual_track_id = item["id"]
    app.audio.status = "DEMO / NO AUDIO"
    app.audio.enabled = False
    app.audio.bars = [0.16 + 0.76 * (0.5 + 0.5 * math.sin(index * 0.49)) for index in range(32)]
    return app


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def choose_font(requested):
    if requested:
        return str(requested)
    candidates = (
        "/usr/share/fonts/Adwaita/AdwaitaMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise SystemExit("Install a monospace font with Braille coverage, or pass --font PATH.")


def measure(app, frames=120):
    app.render()
    samples = []
    for _ in range(frames):
        started = time.perf_counter()
        app.render()
        samples.append((time.perf_counter() - started) * 1000)
    return {
        "frames": frames,
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "assets")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--font", type=Path, help="monospace font with Braille glyphs")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    font_path = choose_font(args.font)

    install_headless_curses()
    with tempfile.TemporaryDirectory(prefix="tspotify-editorial-") as data_dir:
        ui.API = demo.Demo()
        ui.DEMO_MODE = True
        ui.NO_SPLASH = True
        ui.NO_MOTION = False
        ui.LOW_POWER = False
        ui.ART = Path(data_dir) / "art"
        ui.ART.mkdir()
        ui.CONFIG = Path(data_dir) / "layout.json"
        ui.cached = lambda name, default: default
        ui.cover = lambda *unused: demo.picture()
        ui.thumbnail = lambda *unused: demo.picture(24, 24)
        ui.Audio = lambda **unused: SimpleNamespace(
            bars=[0.0] * 32, enabled=False, status="DEMO / NO AUDIO", close=lambda: None
        )

        timings = {}
        for name, size in (
            ("80x24", (24, 80)),
            ("120x40", (40, 120)),
            ("160x50", (50, 160)),
        ):
            app = ready_app(size)
            app.render()
            image_for(app, font_path).save(args.output / f"editorial-main-{name}.png")
            timings[f"main_{name}"] = measure(app, args.frames)
            if name in ("80x24", "120x40", "160x50"):
                app.fullscreen = True
                app.render()
                image_for(app, font_path).save(args.output / f"editorial-player-{name}.png")
                timings[f"player_{name}"] = measure(app, args.frames)

            if name == "120x40":
                old_art = app.art
                app.art_transition = (old_art, time.monotonic() + 1, 0.28)
                timings["cover_transition_120x40"] = measure(app, args.frames)
                app.art_transition = None

                app.fullscreen = False
                app.render()
                source = app._display_grid.clone()
                app.fullscreen = True
                app.panel_transition = (source.clone(), time.monotonic() + 1, 0.21)
                timings["panel_transition_120x40"] = measure(app, args.frames)
                app.panel_transition = None

                panel_frames = []
                duration = 0.21
                for frame in range(11):
                    progress = frame / 10
                    app.panel_transition = (source.clone(), time.monotonic() - progress * duration, duration)
                    app.render()
                    panel_frames.append(image_for(app, font_path))
                panel_frames[0].save(
                    args.output / "editorial-panel-transition.gif",
                    save_all=True,
                    append_images=panel_frames[1:],
                    duration=28,
                    loop=0,
                    optimize=False,
                )

                app.fullscreen = True
                old_art = demo.picture()
                new_art = [[(pixel[2], pixel[0], pixel[1]) for pixel in row] for row in old_art]
                app.art = new_art
                cover_frames = []
                duration = 0.28
                for frame in range(13):
                    progress = frame / 12
                    app.art_transition = (old_art, time.monotonic() - progress * duration, duration)
                    app.render()
                    cover_frames.append(image_for(app, font_path))
                cover_frames[0].save(
                    args.output / "editorial-cover-transition.gif",
                    save_all=True,
                    append_images=cover_frames[1:],
                    duration=24,
                    loop=0,
                    optimize=False,
                )
            close_app(app)

        timings["measurement"] = {
            "method": "FakeScreen render loop, no Spotify account, network, audio capture or terminal I/O",
            "python": sys.version.split()[0],
            "frames_per_layout": args.frames,
        }
        (args.output / "editorial-render-benchmark.json").write_text(
            json.dumps(timings, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(timings, indent=2))


if __name__ == "__main__":
    main()
