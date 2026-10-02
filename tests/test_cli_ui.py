"""Tests sloppy.cli_ui - the single-line spinner + ok/warn/fail/skip helpers. Each test
swaps in a Console that writes to a StringIO with terminal detection forced off, so the
assertions don't depend on whether the test runner's stdout looks like a TTY (some
environments set FORCE_COLOR etc., which makes the module-level console emit ANSI)."""

import io

import pytest
from rich.console import Console

from sloppy import cli_ui


@pytest.fixture
def buf(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(
        cli_ui,
        "console",
        Console(file=stream, force_terminal=False, color_system=None, highlight=False),
    )
    return stream


def test_result_helpers_print_prefixed_lines(buf):
    cli_ui.ok("a done")
    cli_ui.skip("b skipped")
    cli_ui.warn("c odd")
    cli_ui.fail("d broke")
    out = buf.getvalue()
    assert "[ok] a done" in out
    assert "[skip] b skipped" in out
    assert "[warn] c odd" in out
    assert "[FAIL] d broke" in out


def test_message_with_brackets_is_not_parsed_as_markup(buf):
    cli_ui.ok("channel [bold]x[/bold] fine")
    assert "channel [bold]x[/bold] fine" in buf.getvalue()


def test_spinner_is_noop_when_not_a_tty_and_messages_still_print(buf):
    with cli_ui.spinner("working") as status:
        status.update("still working")
        cli_ui.ok("one")
    out = buf.getvalue()
    assert "[ok] one" in out
    assert "\r" not in out
    assert "still working" not in out


def test_force_terminal_on_in_git_bash(monkeypatch):
    monkeypatch.delenv("SLOP_PLAIN", raising=False)
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert cli_ui._force_terminal() is True


def test_force_terminal_defers_to_rich_outside_git_bash(monkeypatch):
    monkeypatch.delenv("SLOP_PLAIN", raising=False)
    monkeypatch.delenv("MSYSTEM", raising=False)
    assert cli_ui._force_terminal() is None


def test_slop_plain_opts_out_even_in_git_bash(monkeypatch):
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("SLOP_PLAIN", "1")
    assert cli_ui._force_terminal() is False
