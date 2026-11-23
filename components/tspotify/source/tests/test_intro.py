import queue

import curses

from tspotify import intro as intro_module, ui
from tspotify.intro import DURATION, FPS, READY_HOLD, Intro, composition, field
from tspotify.ui import App


def test_intro_fits_wide_terminal_without_touching_text_column():
    layout = composition(160, 48, rows=3)

    assert layout.graphic is not None
    y, x, width, height = layout.graphic
    assert x >= layout.x + 41
    assert x + width <= layout.x + layout.width
    assert y + height < layout.rule
    assert layout.rule < 48


def test_intro_compacts_to_narrow_terminal():
    layout = composition(80, 24, rows=2)

    assert layout.graphic is not None
    y, x, width, height = layout.graphic
    assert x == layout.x
    assert width <= layout.width
    assert y + height < layout.rule < 24
    assert layout.info_y > layout.y + 2 + len(layout.subtitle)


def test_very_small_terminal_suppresses_graphic_instead_of_clipping_it():
    layout = composition(35, 12, rows=3)

    assert layout.graphic is None
    assert layout.rule is None


def test_generator_returns_transparent_background_and_two_visual_forms():
    image = field(72, 7, phase=0.2)

    assert len(image) == 28
    assert all(len(row) == 144 for row in image)
    assert image[0][0] == (0, 0, 0)
    assert any(pixel[1] > pixel[0] for row in image for pixel in row)
    assert any(pixel[2] > pixel[0] for row in image for pixel in row)


def test_intro_uses_brief_fifteen_fps_interval():
    assert 1.5 <= DURATION <= 2.5
    assert 2.0 <= READY_HOLD <= 4.0
    assert 1 <= FPS <= 20


def test_intro_expiry_is_monotonic_duration_based():
    intro = Intro(10.0, motion=False)

    assert not intro.expired(11.99)
    assert intro.expired(12.0)


def test_control_hotkey_skips_intro_without_enqueuing_player_action():
    app = App.__new__(App)
    app.intro_active = True
    app.intro_skip_requested = False
    app.skip_input_until = 0
    app.events = queue.Queue()

    app.route_control("play-pause")

    assert app.intro_skip_requested
    assert app.events.empty()


def test_any_key_skips_intro_but_resize_is_only_a_redraw():
    app = App.__new__(App)

    assert app.intro_key("x")
    assert not app.intro_key(curses.KEY_RESIZE)


def test_static_intro_redraws_after_resize_then_stays_still():
    class Screen:
        size = (48, 160)

        def getmaxyx(self):
            return self.size

        def erase(self):
            pass

        def refresh(self):
            pass

    class Renderer:
        def __init__(self):
            self.s = Screen()
            self.frames = []

        def put(self, *args, **kwargs):
            pass

        def symbol_image(self, image, y, x, width, height, **kwargs):
            self.frames.append((len(image[0]), len(image), x, y, width, height))

    renderer = Renderer()
    intro = Intro(0, motion=False)
    intro.draw(renderer, 0)
    intro.draw(renderer, 0.5)
    renderer.s.size = (24, 80)
    intro.draw(renderer, 0.6)

    assert len(renderer.frames) == 2
    assert renderer.frames[0][-2:] == (87, 17)
    assert renderer.frames[1][-2:] == (74, 7)
    assert renderer.frames[1][2:4] == (3, 11)


def test_startup_screen_starts_engine_and_returns_its_error(monkeypatch):
    class Screen:
        size = (24, 80)

        def getmaxyx(self):
            return self.size

        def addnstr(self, *args):
            pass

        def get_wch(self):
            raise curses.error

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    for name in ("start_color", "use_default_colors", "init_pair"):
        monkeypatch.setattr(curses, name, lambda *args: None)
    monkeypatch.setattr(curses, "has_colors", lambda: True)
    monkeypatch.setattr(curses, "color_pair", lambda pair: pair)
    monkeypatch.setattr(curses, "COLORS", 256, raising=False)
    monkeypatch.setattr(curses, "COLOR_PAIRS", 65536, raising=False)
    monkeypatch.setattr(ui, "NO_MOTION", True)
    monkeypatch.setattr(ui, "ASCII_ONLY", True)
    monkeypatch.setattr(intro_module, "DURATION", 0)
    monkeypatch.setattr(intro_module, "READY_HOLD", 0)
    calls = []

    error = ui.startup_screen(Screen(), lambda: calls.append("engine-ready"))

    assert error is None
    assert calls == ["engine-ready"]
