"""Explicit offline preview: no account access, devices, or audio playback."""

import copy
import curses
import math
import os
import time
from types import SimpleNamespace


def picture(width=128, height=128):
    result = []
    for y in range(height):
        row = []
        for x in range(width):
            nx, ny = x / width, y / height
            if (nx - 0.72) ** 2 + (ny - 0.25) ** 2 < 0.014:
                pixel = (215, 195, 170)
            elif ny > 0.62 + 0.12 * math.sin(nx * 9):
                pixel = (40 + int(nx * 35), 68 + int(nx * 28), 88 + int(nx * 30))
            else:
                pixel = (45 + int(ny * 55), 62 + int(nx * 65), 115 + int(ny * 60))
            row.append(pixel)
        result.append(row)
    return result


class Demo:
    backend = None

    def __init__(self):
        self.started = time.monotonic()
        self.playing = False
        self.volume = 0
        self.saved = False
        self.current = 0
        self.tracks = [
            dict(
                id=str(i),
                name=name,
                type="track",
                artists=[{"name": artist}],
                album={"id": "demo", "name": "After Hours", "images": [{"url": "demo:cover"}]},
                duration_ms=240000,
            )
            for i, (name, artist) in enumerate(
                [
                    ("Night Drive", "Ghosts on Tape"),
                    ("Soft Signals", "Moonlight Arcade"),
                    ("Last Train Home", "The Quiet Hours"),
                    ("A Room Above the City", "Blue Static"),
                ]
            )
        ]

    def playback(self):
        return {
            "item": self.tracks[self.current],
            "is_playing": self.playing,
            "progress_ms": int((time.monotonic() - self.started) * 1000) % 240000 if self.playing else 84000,
            "device": {"name": "DEMO / no audio", "volume_percent": self.volume},
            "repeat_state": "off",
        }

    def library(self, section):
        kind = (
            "album"
            if section in ("Альбомы", "Новые релизы")
            else "track"
            if section in ("Любимые", "Недавние", "Рекомендации")
            else "playlist"
        )
        items = (
            self.tracks
            if kind == "track"
            else [
                {"id": str(i), "name": name, "owner": ["tspotify demo"]}
                for i, name in enumerate(["Midnight Sessions", "Focus Mixes", "After Hours", "Slow Sunday"])
            ]
        )
        return section, [(kind, copy.deepcopy(item)) for item in items]

    def context(self, kind, item_id, name):
        return {
            "name": name,
            "tracks": copy.deepcopy(self.tracks),
            "context_uri": "demo:" + kind + ":" + item_id,
        }

    def start(self, item):
        self.current = int(item["id"]) % len(self.tracks)
        self.playing = True
        self.started = time.monotonic()
        return "ДЕМО: трек выбран, звук не воспроизводится"

    def start_context(self, kind, item):
        return self.start(self.tracks[0])

    def control(self, command, value=None):
        if command == "play-pause":
            self.playing = not self.playing
        elif command == "next":
            self.current = (self.current + 1) % len(self.tracks)
        elif command == "previous":
            self.current = (self.current - 1) % len(self.tracks)
        elif command == "volume":
            self.volume = max(0, min(100, int(value)))
        return "ДЕМО / звук выключен"

    def start_jam(self):
        raise RuntimeError("В деморежиме Jam не создаётся. Войдите в Spotify в обычном режиме.")

    def toggle_favorite(self, track_id):
        self.saved = not self.saved
        return self.saved

    def search(self, query):
        return {
            "tracks": [
                copy.deepcopy(x)
                for x in self.tracks
                if query.lower() in (x["name"] + " " + x["artists"][0]["name"]).lower()
            ]
        }


def run(args):
    from . import ui, paths

    ui.API = Demo()
    ui.ASCII_ONLY = args.ascii
    ui.NO_SPLASH = args.no_splash
    ui.NO_MOTION = args.no_motion or os.environ.get("TSPOTIFY_REDUCED_MOTION", "").lower() in (
        "1",
        "true",
        "yes",
    )
    ui.LOW_POWER = args.low_power or os.environ.get("TSPOTIFY_LOW_POWER", "").lower() in (
        "1",
        "true",
        "yes",
    )
    ui.DEMO_MODE = True
    ui.ART = paths.CACHE / "demo"
    ui.ART.mkdir(exist_ok=True)
    ui.CONFIG = paths.CONFIG / "demo-layout.json"
    ui.cached = lambda name, default: default
    ui.cover = lambda *args: picture()
    ui.thumbnail = lambda *args: picture(24, 24)
    ui.Audio = lambda **kwargs: SimpleNamespace(
        bars=[0.3 + 0.3 * math.sin(i / 8) ** 2 for i in range(32)],
        enabled=True,
        status="DEMO / no capture",
        close=lambda: None,
    )
    curses.wrapper(lambda screen: ui.App(screen).run())
