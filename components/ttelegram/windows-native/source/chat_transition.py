"""Shared four-state timing and glyphs for chat-open transitions."""

CHAT_TRANSITION_SECONDS = .42
CHAT_TRANSITION_GLYPHS = ('·', '◦', '○', '●')
CHAT_TRANSITION_STATE_COUNT = len(CHAT_TRANSITION_GLYPHS)


def chat_transition_state(age):
    """Return one of four visible transition states from elapsed time."""
    age = max(0.0, float(age))
    return min(CHAT_TRANSITION_STATE_COUNT - 1,
               int(age / (CHAT_TRANSITION_SECONDS / CHAT_TRANSITION_STATE_COUNT)))
