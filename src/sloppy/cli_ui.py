"""Terminal progress UI for long-running CLI commands.

`spinner` keeps a single live status line at the bottom of the terminal; `ok`/`warn`/`fail`
print above it, so each result scrolls up while the spinner keeps going for the next unit
of work. rich disables the live line automatically when stdout isn't a TTY, so piped/logged
output stays plain.
"""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.markup import escape
from rich.status import Status


def _force_terminal() -> bool | None:
    """Git Bash (mintty) hands Python a pipe instead of a TTY, so rich concludes it is
    not interactive and silently disables the live spinner - even though mintty renders
    ANSI fine. Force it on there. SLOP_PLAIN=1 opts out (e.g. when redirecting to a
    file from Git Bash); None leaves rich's own detection alone everywhere else."""
    if os.environ.get("SLOP_PLAIN"):
        return False
    if os.environ.get("MSYSTEM") and os.environ.get("TERM"):
        return True
    return None


console = Console(highlight=False, force_terminal=_force_terminal())


def _spinner_name() -> str:
    """Braille 'dots' needs a UTF-8 stdout; fall back to ASCII on e.g. a cp1252 Windows
    console so the spinner doesn't raise UnicodeEncodeError."""
    try:
        "⠋".encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return "line"
    return "dots"


@contextmanager
def spinner(message: str) -> Iterator[Status]:
    """Yields the rich Status; call `.update("...")` to change the text (e.g. per channel)."""
    with console.status(escape(message), spinner=_spinner_name()) as status:
        yield status


def _tagged(style: str, tag: str, message: str) -> None:
    # Console.print would parse a bare "[ok]" as a markup tag, so build it with Text-safe
    # escaping: escape() backslash-escapes the opening bracket.
    console.print(f"[{style}]{escape(f'[{tag}]')}[/{style}] {escape(message)}")


def ok(message: str) -> None:
    _tagged("green", "ok", message)


def skip(message: str) -> None:
    _tagged("dim", "skip", message)


def warn(message: str) -> None:
    _tagged("yellow", "warn", message)


def fail(message: str) -> None:
    _tagged("red", "FAIL", message)
