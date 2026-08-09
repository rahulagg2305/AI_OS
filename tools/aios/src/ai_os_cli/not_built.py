"""One real, shared way to declare a documented (`cli_design.md` §4)
but not-yet-backed command: it stays discoverable (``--help`` still
shows it) and, run, fails clearly with the real reason no HTTP
endpoint exists — never silently omitted, never a fabricated success.
"""

from __future__ import annotations

from ai_os_cli.errors import EXIT_GENERAL_ERROR, CliError


def not_yet_implemented(reason: str) -> None:
    raise CliError(f"not yet implemented: {reason}", exit_code=EXIT_GENERAL_ERROR)
