"""``aios config`` — ``get``/``set``/``flags`` (``cli_design.md`` §4).
All three are real: ``ai_os_kernel.routes.config`` already exposes
every one of this documented group's own operations. Named
``config_cmd`` (not ``config``) to avoid shadowing this CLI's own
:mod:`ai_os_cli.config` module."""

from __future__ import annotations

import json as json_module

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.errors import EXIT_USAGE_ERROR, CliError
from ai_os_cli.output import render

app = typer.Typer(help="Read/write non-security runtime configuration.")


@app.command()
def get(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/config")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command(name="set")
def set_value(
    ctx: typer.Context,
    key: str,
    value: str = typer.Argument(..., help="A JSON value, e.g. 'true' or '\"prod\"' or '42'."),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    try:
        parsed_value = json_module.loads(value)
    except json_module.JSONDecodeError as exc:
        raise CliError(f"value is not valid JSON: {exc}", exit_code=EXIT_USAGE_ERROR) from exc

    client = AiosClient(load_config())
    try:
        response = client.patch(
            "/api/v1/config",
            json={"config_key": key, "new_value": parsed_value, "reason": reason},
        )
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def flags(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/config/flags")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
