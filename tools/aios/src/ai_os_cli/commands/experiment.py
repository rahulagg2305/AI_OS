"""``aios experiment`` — declared (``cli_design.md`` §4) but not built:
no ``/api/v1/experiments`` HTTP route exists in production at all
(`feature_inventory.md` module 34, Benchmarking Pack, is 28% built —
real pack internals, but no API surface yet) — every subcommand fails
clearly, rather than being silently omitted from ``--help``."""

from __future__ import annotations

import typer

from ai_os_cli.not_built import not_yet_implemented

app = typer.Typer(help="Trigger or inspect experiments.")

_REASON = "no /api/v1/experiments route exists in production yet"


@app.command()
def create() -> None:
    not_yet_implemented(_REASON)


@app.command()
def run(experiment_id: str) -> None:
    not_yet_implemented(_REASON)


@app.command()
def show(experiment_id: str) -> None:
    not_yet_implemented(_REASON)


@app.command()
def compare(experiment_id: str) -> None:
    not_yet_implemented(_REASON)
