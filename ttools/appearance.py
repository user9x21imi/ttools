"""Keep the current terminal profile, background and opacity untouched."""
from contextlib import contextmanager

@contextmanager
def konsole_profile():
    # Retain the integration boundary without switching the user's terminal theme.
    yield None
