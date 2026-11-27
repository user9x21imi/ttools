"""Create reproducible offline screenshots, a transition GIF, and render timings."""

import curses
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tspotify import ui  # noqa: E402
from tspotify.demo import Demo, picture  # noqa: E402


OUT = ROOT / "docs" / "qa-artifacts"
WIDTH, HEIGHT = 120, 40
CELL_W, CELL_H = 11, 21
BACKGROUND = (17, 20, 22)
PAIRS = {}


class Window:
    def __init__(self):
        self.size = HEIGHT, WIDTH

    def getmaxyx(self):
        return self.size

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def palette(index):
    base = [
        (0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16),
        (36, 114, 200), (188, 63, 188), (17, 168, 205), (229, 229, 229),
        (102, 102, 102), (241, 76, 76), (35, 209, 139), (245, 245, 67),
        (59, 142, 234), (214, 112, 214), (41, 184, 219), (255, 255, 255),
    ]
    if index < 16:
        return base[index]
    if index < 232:
        value = index - 16
        levels = (0, 95, 135, 175, 215, 255)
        return levels[value // 36], levels[(value // 6) % 6], levels[value % 6]
    level = 8 + (index - 232) * 10
    return level, level, level


def cell_colors(cell):
    if cell.color in PAIRS:
        return PAIRS[cell.color]
    semantic = {
        1: (230, 231, 224), 2: (72, 213, 131), 3: (135, 184, 222),
        4: (143, 148, 145), 5: (240, 204, 120), 6: (235, 239, 228),
        7: (178, 158, 225), 8: (227, 123, 131), 9: (25, 29, 31),
        10: (82, 88, 90), 11: (91, 99, 96), 12: (96, 173, 120),
    }
    return semantic.get(cell.color, (170, 177, 174)), None


def load_font(bold=False):
    candidates = (
        (
            "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf",
            "C:/Windows/Fonts/consolab.ttf",
            "/System/Library/Fonts/Menlo.ttc",
        )
        if bold
        else (
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
            "C:/Windows/Fonts/consola.ttf",
            "/System/Library/Fonts/Menlo.ttc",
        )
    )
    path = next((item for item in candidates if os.path.exists(item)), None)
    return ImageFont.truetype(path, 15) if path else ImageFont.load_default()


def image_for(grid):
    image = Image.new("RGB", (grid.width * CELL_W, grid.height * CELL_H), BACKGROUND)
    draw = ImageDraw.Draw(image)
    regular = load_font()
    bold = load_font(bold=True)
    for y, row in enumerate(grid.cells):
        for x, cell in enumerate(row):
            fg, bg = cell_colors(cell)
            left, top = x * CELL_W, y * CELL_H
            if bg is not None:
                draw.rectangle((left, top, left + CELL_W - 1, top + CELL_H - 1), fill=bg)
            if cell.glyph and "\u2800" <= cell.glyph <= "\u28ff":
                bits = ord(cell.glyph) - 0x2800
                positions = ((1, 2, 3), (2, 2, 8), (4, 2, 13), (8, 7, 3), (16, 7, 8), (32, 7, 13), (64, 2, 18), (128, 7, 18))
                for bit, dx, dy in positions:
                    if bits & bit:
                        draw.ellipse((left + dx - 1, top + dy - 1, left + dx + 1, top + dy + 1), fill=fg)
            elif cell.glyph and cell.glyph != " ":
                draw.text((left, top - 1), cell.glyph, font=bold if cell.bold else regular, fill=fg)
    return image


def render(app):
    app.render()
    return image_for(app._last_grid)


def transition_frames(app, fullscreen):
    source = app._display_grid.clone()
    app.fullscreen = fullscreen
    start = time.monotonic() + 1
    app.panel_transition = (source, start, 0.21)
    app.render()
    frames = [image_for(app._display_grid)]
    for offset in (0.025, 0.05, 0.075, 0.1, 0.125, 0.15, 0.175, 0.205, 0.23):
        app._finish_render(now=start + offset)
        frames.append(image_for(app._display_grid))
    return frames


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("start_color", "use_default_colors", "init_pair", "curs_set"):
        setattr(curses, name, lambda *args: None)
    curses.has_colors = lambda: True
    curses.color_pair = lambda value: value
    curses.COLORS = 256
    curses.COLOR_PAIRS = 65536

    def remember_pair(pair, fg, bg):
        PAIRS[pair] = (palette(fg), None if bg < 0 else palette(bg))

    curses.init_pair = remember_pair
    ui.NO_SPLASH = True
    ui.NO_MOTION = False
    ui.LOW_POWER = False
    ui.ASCII_ONLY = False
    ui.DEMO_MODE = True
    ui.API = Demo()
    ui.cached = lambda name, default: default
    ui.cover = lambda *args: picture()
    ui.thumbnail = lambda *args: picture(24, 24)
    ui.Audio = lambda **kwargs: SimpleNamespace(
        bars=[0.4] * 32, enabled=True, status="DEMO / no capture", close=lambda: None
    )

    with tempfile.TemporaryDirectory(prefix="tspotify-qa-") as temp:
        ui.ART = Path(temp) / "art"
        ui.ART.mkdir()
        ui.CONFIG = Path(temp) / "layout.json"
        app = ui.App(Window())
        try:
            for _ in range(100):
                app.drain()
                if not app.pending:
                    break
                time.sleep(0.005)
            app.playback = ui.API.playback()
            app.updated = time.monotonic()
            app.art = picture()
            app.thumbnails["album:demo-album-1"] = picture(24, 24)
            app.thumbnails["album:demo-album-2"] = picture(24, 24)
            app.thumbnails["artist:demo-artist"] = picture(24, 24)
            app.section = "Плейлисты"
            app.items = ui.API.library("Плейлисты")[1]
            app.selected = 0
            app.fullscreen = False
            app.panel_transition = None
            render(app).save(OUT / "library-120x40.png")

            app.fullscreen = True
            app.panel_transition = None
            render(app).save(OUT / "player-120x40.png")
            app.fullscreen = False

            profile = ui.API.artist_profile("demo-artist", "Ghosts on Tape")
            app.artist_profile = profile
            app.artist_group = "all"
            app.section = "ARTIST / Ghosts on Tape"
            app.items = app.artist_items(profile, "all")
            app.selected = 0
            app.panel_transition = None
            render(app).save(OUT / "artist-profile-120x40.png")
            app.artist_profile = None
            app.section = "Плейлисты"
            app.items = ui.API.library("Плейлисты")[1]
            app.selected = 0
            app.panel_transition = None
            app.fullscreen = False
            app.render()

            frames = transition_frames(app, True)
            frames.extend(transition_frames(app, False)[1:])
            frames[0].save(
                OUT / "f3-transition.gif",
                save_all=True,
                append_images=frames[1:],
                duration=35,
                loop=0,
                optimize=True,
            )

            timings = []
            app.panel_transition = None
            app.fullscreen = False
            for _ in range(40):
                started = time.perf_counter()
                app.render()
                timings.append((time.perf_counter() - started) * 1000)
            timings.sort()
            p95 = timings[int((len(timings) - 1) * 0.95)]
            (OUT / "performance.txt").write_text(
                "Offline demo rendering · 120×40 terminal · 40 frames\n"
                f"mean render: {statistics.mean(timings):.2f} ms\n"
                f"p95 render: {p95:.2f} ms\n"
                f"max render: {max(timings):.2f} ms\n",
                encoding="utf-8",
            )
        finally:
            app.search_pool.shutdown(wait=True, cancel_futures=True)
            app.state_pool.shutdown(wait=True, cancel_futures=True)
            app.transport_pool.shutdown(wait=True, cancel_futures=True)
            app.pool.shutdown(wait=True, cancel_futures=True)
            app.art_pool.shutdown(wait=True, cancel_futures=True)
            app.cover_pool.shutdown(wait=True, cancel_futures=True)
    print(f"Wrote offline QA captures to {OUT}")


if __name__ == "__main__":
    main()
