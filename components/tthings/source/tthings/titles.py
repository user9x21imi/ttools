"""Shared activity captions for terminal tabs and desktop effect windows."""
from .catalog import BUILTINS

def effect_caption(effect_id):
    entry=next(e for e in BUILTINS if e.id==effect_id)
    return f'{entry.title} ({entry.id}) · Beautiful Things'

def system_caption(title):return f'{title} · Systems Things'
