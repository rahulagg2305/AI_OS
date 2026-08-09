"""Real dual-mode output (``cli_design.md`` §4: "``--output human``
(Rich, default when a TTY) or ``--output json`` (default when
piped)") — the actual TTY-detection rule, not a fixed default that
ignores how the CLI is actually being invoked.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

_console = Console()


def resolve_output_format(explicit: str | None) -> str:
    """``explicit`` (``--output``) always wins. Otherwise: human for a
    real interactive terminal, json for anything piped or redirected —
    a script capturing this CLI's stdout gets machine-readable output
    without needing to pass the flag itself."""
    if explicit is not None:
        return explicit
    return "human" if sys.stdout.isatty() else "json"


def render(data: Any, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    _render_human(data)


def _render_human(data: Any) -> None:
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        _render_table(data)
    elif isinstance(data, dict):
        _render_table([data])
    elif isinstance(data, list) and not data:
        _console.print("(no results)")
    else:
        _console.print(data)


def _render_table(rows: list[dict[str, Any]]) -> None:
    # Column order: every key any row actually has, first-seen order —
    # real data drives the shape, never a hardcoded column list that
    # would silently drop a field a future endpoint adds.
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    table = Table()
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*(_cell(row.get(column)) for column in columns))
    _console.print(table)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)
