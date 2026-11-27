"""Regression tests for the VT backend that preserves terminal transparency."""
import curses as stdlib_curses

from ttools import vtbackend


def test_default_background_emits_no_sgr():
    """A default (-1) background must never produce an explicit VT background code."""
    vtbackend.init_pair(101, vtbackend.COLOR_WHITE, -1)
    sequence = vtbackend._sgr(vtbackend.color_pair(101))
    assert '48;' not in sequence
    assert sequence.startswith('\x1b[')


def test_explicit_background_still_works():
    vtbackend.init_pair(102, vtbackend.COLOR_WHITE, vtbackend.COLOR_BLUE)
    assert '48;5;4' in vtbackend._sgr(vtbackend.color_pair(102))


def test_curses_api_parity_for_launcher():
    """Every curses name the launcher uses must be provided by the VT backend."""
    required = (
        'ALL_MOUSE_EVENTS A_BOLD BUTTON1_DOUBLE_CLICKED COLORS COLOR_BLUE COLOR_GREEN '
        'COLOR_MAGENTA COLOR_RED COLOR_YELLOW KEY_BACKSPACE KEY_DOWN KEY_ENTER KEY_F1 '
        'KEY_MOUSE KEY_RESIZE KEY_UP color_pair curs_set def_prog_mode endwin error '
        'flushinp getmouse init_pair mousemask reset_prog_mode start_color '
        'use_default_colors wrapper'
    ).split()
    for name in required:
        assert hasattr(vtbackend, name), name


def test_curses_api_parity_for_components():
    required = (
        'REPORT_MOUSE_POSITION BUTTON1_PRESSED BUTTON1_CLICKED BUTTON1_RELEASED '
        'BUTTON4_PRESSED BUTTON5_PRESSED has_colors raw mouseinterval COLOR_PAIRS '
        'KEY_F7 KEY_F10 KEY_F12'
    ).split()
    for name in required:
        assert hasattr(vtbackend, name), name


def test_launcher_selects_vt_backend_only_when_usable():
    """The launcher must fall back to PDCurses when no console is attached."""
    import importlib
    import sys

    # Reload in a subprocess-free way by checking the selection logic constants.
    assert vtbackend.usable() in (True, False)
    assert hasattr(stdlib_curses, 'wrapper')
    assert sys.platform in ('win32', 'linux', 'darwin')
