"""``aios pack`` — ``list``/``show``/``activate``/``deactivate``
(``cli_design.md`` §4). All four are real: ``ai_os_kernel.routes.packs``
already exposes every one of this documented group's own operations —
the only real, complete command group this step needed no disclosed
gap for."""

from __future__ import annotations

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.output import render

app = typer.Typer(help="Register/activate/deactivate/inspect Capability Packs.")


@app.command(name="list")
def list_packs(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/packs")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def show(ctx: typer.Context, pack_id: str) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/packs/{pack_id}")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def activate(ctx: typer.Context, pack_id: str, reason: str = typer.Option(..., "--reason")) -> None:
    client = AiosClient(load_config())
    try:
        response = client.post(f"/api/v1/packs/{pack_id}/activate", json={"reason": reason})
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def deactivate(
    ctx: typer.Context, pack_id: str, reason: str = typer.Option(..., "--reason")
) -> None:
    client = AiosClient(load_config())
    try:
        response = client.post(f"/api/v1/packs/{pack_id}/deactivate", json={"reason": reason})
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
