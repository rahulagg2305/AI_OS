"""``aios logs`` — declared (``cli_design.md`` §4) but not built:
Observability has no log-query HTTP endpoint (logs go to structlog/an
OTLP collector, never a Kernel route a CLI could call)."""

from __future__ import annotations

import typer

from ai_os_cli.not_built import not_yet_implemented

app = typer.Typer(help="Tail or search platform logs.")

_REASON = "Observability has no log-query route"


@app.command()
def tail() -> None:
    not_yet_implemented(_REASON)


@app.command()
def search(query: str) -> None:
    not_yet_implemented(_REASON)
