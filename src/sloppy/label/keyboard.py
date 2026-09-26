"""Single-keystroke input for the labeling CLI.

Actual key capture (readchar) is isolated in read_key() so the pure key -> action mapping
below can be unit tested without a real terminal.
"""

import readchar

KEY_ACTIONS: dict[str, str] = {
    "y": "up",
    "n": "down",
    "s": "skip",
    "q": "quit",
}


def action_for_key(key: str) -> str | None:
    return KEY_ACTIONS.get(key.lower())


def read_key() -> str:
    return readchar.readkey()
