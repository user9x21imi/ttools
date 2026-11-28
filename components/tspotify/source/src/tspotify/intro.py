"""Local, decorative startup geometry. No audio, account data, IO or subprocesses."""

from dataclasses import dataclass
import math
import os
import platform
import textwrap

from . import __version__

DURATION = 2.0
READY_HOLD = 3.0
FPS = 15
TAGLINE = "Музыка задаёт пространство"
MODES = {"dots": "Braille / точки", "ascii": "ASCII", "blocks": "Полутона"}


@dataclass(frozen=True)
class Composition:
    x: int
    y: int
    width: int
    graphic: tuple | None
    rule: int | None
    info_y: int
    subtitle: tuple[str, ...]


def composition(width, height, rows=3):
    margin = 3 if width >= 64 else 2 if width >= 20 else 0
    usable = max(1, min(128, width - margin * 2))
    x = max(margin, (width - usable) // 2)
    if width >= 104 and height >= 20:
        gh = min(17, height - 6)
        y = max(1, (height - gh - 3) // 2)
        return Composition(x, y, usable, (y, x + 41, usable - 41, gh), y + gh + 1, y + 6, (TAGLINE,))
    subtitle = tuple(textwrap.wrap(TAGLINE, usable))
    y = max(1, (height - 21) // 2)
    info_y = y + 3 + len(subtitle)
    gy = info_y + rows + 1
    gh = min(7, height - gy - 4)
    graphic = (gy, x, usable, gh) if usable >= 40 and gh >= 4 else None
    rule = (gy + gh + 1 if graphic else info_y + rows + 1) if width >= 64 and height >= 18 else None
    return Composition(x, y, usable, graphic, rule, info_y, subtitle)


def field(width, height, phase, reveal=1.0):
    """Sample two original parametric forms for the existing terminal artwork renderer."""
    pw, ph = width * 2, height * 4
    image = [[(0, 0, 0)] * pw for _ in range(ph)]
    green, accent = (72, 205, 126), (66, 133, 127)

    def point(x, y, color, strength=1.0):
        ix, iy = round(x), round(y)
        if 0 <= ix < pw and 0 <= iy < ph:
            value = tuple(int(c * min(1.0, reveal * strength)) for c in color)
            if sum(value) > sum(image[iy][ix]):
                image[iy][ix] = value

    def line(a, b, color, strength=1.0):
        steps = max(1, math.ceil(max(abs(a[0] - b[0]), abs(a[1] - b[1]))))
        for n in range(steps + 1):
            t = n / steps
            point(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, color, strength)

    # Quiet, drifting streamlines: decoration, never a simulated audio spectrum.
    for ribbon in range(7):
        previous = None
        for i in range(max(40, pw // 2)):
            t = i / max(1, max(40, pw // 2) - 1)
            envelope = math.sin(math.pi * t) ** 0.65
            x = pw * (0.015 + t * 0.57)
            y = ph * (
                0.49 + (ribbon - 3) * 0.073 + envelope * (0.11 * math.sin(t * 9 - phase + ribbon * 0.22))
            )
            current = (x, y)
            if previous:
                line(previous, current, accent if ribbon % 3 == 0 else green, 0.58 + ribbon * 0.035)
            previous = current

    # A twisted, projected sheet: longitudinal ribs and curved cross sections.
    def project(u, v):
        twist = u * 0.84 + 0.28 * math.sin(phase * 0.3)
        yy = v * math.cos(twist) + 0.22 * math.sin(u * 1.6)
        zz = v * math.sin(twist) + 0.22 * math.cos(u * 1.25)
        return (pw * (0.745 + u * 0.092 + zz * 0.032), ph * (0.49 + yy * 0.29 - zz * 0.12))

    for j in range(17):
        v = -1 + j / 8
        previous = None
        for i in range(85):
            current = project(-2.35 + i / 84 * 4.7, v)
            if previous:
                line(previous, current, green, 0.76 + 0.19 * math.cos(v * 1.1))
            previous = current
    for j in range(33):
        u = -2.35 + j / 32 * 4.7
        previous = None
        for i in range(25):
            current = project(u, -1 + i / 12)
            if previous:
                line(previous, current, accent if j % 8 == 0 else green, 0.62)
            previous = current
    return image


class Intro:
    def __init__(self, started, *, motion=True, art_mode=None, ascii_only=False):
        self.started = started
        self.motion = motion
        self.art_mode = art_mode
        self.ascii_only = ascii_only
        self.size = None
        self.drawn_status = None
        self.status = "Подключаем клиент Spotify…"
        self.finished = False
        self.info = [
            ("Система", platform.platform(aliased=True, terse=True)),
            ("Архитектура", platform.machine()),
            ("Python", platform.python_version()),
            ("Терминал", os.environ.get("TERM_PROGRAM") or os.environ.get("TERM") or "Windows Terminal"),
            ("tspotify", __version__),
        ]
        if art_mode in MODES:
            self.info.append(("Визуализация", MODES[art_mode]))

    def expired(self, now):
        return now - self.started >= DURATION

    def draw(self, app, now):
        height, width = app.s.getmaxyx()
        changed = self.size != (height, width)
        status_changed = self.drawn_status != self.status
        if not changed and not self.motion and not status_changed:
            return
        elapsed = max(0, now - self.started)
        layout = composition(width, height, len(self.info))
        app._panel_x, app._panel_width = 0, width
        if changed or status_changed:
            app.s.erase()
        if changed or status_changed:
            app.put(layout.y, layout.x, "tspotify", 2, True, width=layout.width)
            app.put(layout.y, layout.x + min(12, layout.width), "SYSTEM / FASTFETCH", 4, width=max(0, layout.width - 12))
            for n, text in enumerate(layout.subtitle):
                app.put(layout.y + 2 + n, layout.x, text, 1, width=layout.width)
            for n, (label, value) in enumerate(self.info):
                # Compact terminals keep labels and values on the same clean line.
                app.put(layout.info_y + n, layout.x, label, 4, width=min(14, layout.width))
                app.put(layout.info_y + n, layout.x + 15, value, 1, width=max(0, layout.width - 15))
            if layout.rule is not None:
                app.put(
                    layout.rule,
                    layout.x,
                    ("-" if self.ascii_only else "─") * layout.width,
                    11,
                    width=layout.width,
                )
        status_y = layout.rule + 1 if layout.rule is not None else height - 2
        app.put(status_y, layout.x, self.status, 4, width=layout.width)
        if layout.graphic:
            y, x, gw, gh = layout.graphic
            phase = elapsed * 0.55 if self.motion else 0
            reveal = min(1.0, 0.25 + elapsed / 0.22) if self.motion else 1.0
            image = field(gw, gh, phase, reveal)
            app.symbol_image(image, y, x, gw, gh, ascii_only=self.ascii_only or self.art_mode == "ascii")
        app.s.refresh()
        self.size = (height, width)
        self.drawn_status = self.status
