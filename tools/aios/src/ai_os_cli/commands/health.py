"""``aios health`` — ``live``/``ready`` (``cli_design.md`` §4). No
``detail`` command: ``ready`` already returns the real, full
per-component detail (``ai_os_kernel.health.HealthService``), so a
separate endpoint/command would only duplicate it."""

from __future__ import annotations

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.output import render

app = typer.Typer(help="Kernel liveness/readiness.")


@app.command()
def live(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/health/live")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def ready(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
