"""``aios experiment`` — declared (``cli_design.md`` §4) but not built:
the Benchmarking Pack is still 0% built (`feature_inventory.md` module
34) and no experiment submission/read HTTP route exists in production
at all — every subcommand fails clearly, rather than being silently
omitted from ``--help``."""

from __future__ import annotations

import typer

from ai_os_cli.not_built import not_yet_implemented

app = typer.Typer(help="Trigger or inspect experiments.")

_REASON = "the Benchmarking Pack is still 0% built — no experiment route exists"


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
