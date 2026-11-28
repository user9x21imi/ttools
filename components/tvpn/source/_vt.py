"""Select a transparency-preserving curses backend on Windows.

PDCurses paints an explicit background on every cell, covering a transparent
Windows Terminal.  Installed component entry points only put their own source
directory on ``sys.path``, so the shared launcher backend is located relative
to this file instead of imported as a top-level package.
"""
import sys
from pathlib import Path


def select():
    """Install and return the curses-compatible module for this process."""
    import curses
    if sys.platform != 'win32':
        return curses
    # <release-root>/components/tvpn/source/_vt.py
    root = Path(__file__).resolve().parents[3]
    if (root / 'ttools' / 'vtbackend.py').is_file() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from ttools import vtbackend
        if not vtbackend.usable():
            raise OSError('no interactive console')
        sys.modules['curses'] = vtbackend
        return vtbackend
    except Exception:
        return curses
