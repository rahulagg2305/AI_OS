"""``aios workflow`` — ``start``/``list``/``show``/``events``/
``manifest``/``cancel`` (``cli_design.md`` §4). ``manifest`` closed
2026-08-10 (``P06-S01-M36-T04``) once ``GET .../run_manifest`` became
real; ``cancel`` closed the same day once ``POST .../cancel`` did.
``retry`` remains declared but not built — no real, operator-triggered
retry mechanism exists yet (only an internal, automatic-retriable-error
primitive — see ``ai_os_kernel.workflow_engine.service``'s
``retry_after_step_failure``, not the same thing)."""

from __future__ import annotations

import json

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.errors import EXIT_USAGE_ERROR, CliError
from ai_os_cli.not_built import not_yet_implemented
from ai_os_cli.output import render

app = typer.Typer(help="Start and inspect workflow instances.")


@app.command()
def start(
    ctx: typer.Context,
    inputs: str = typer.Option("{}", "--inputs", help="A JSON object of workflow inputs."),
) -> None:
    try:
        parsed_inputs = json.loads(inputs)
    except json.JSONDecodeError as exc:
        raise CliError(f"--inputs is not valid JSON: {exc}", exit_code=EXIT_USAGE_ERROR) from exc

    client = AiosClient(load_config())
    try:
        response = client.post("/api/v1/workflows", json={"inputs": parsed_inputs})
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command(name="list")
def list_workflows(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit"),
    cursor: str | None = typer.Option(None, "--cursor"),
) -> None:
    params = {"limit": limit} | ({"cursor": cursor} if cursor is not None else {})
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/workflows", params=params)
    finally:
        client.close()
    body = response.json()
    render(body["items"], output_format=ctx.obj["output_format"])
    if body["next_cursor"] and ctx.obj["output_format"] == "human":
        typer.echo(f"next page: --cursor {body['next_cursor']}")


@app.command()
def show(ctx: typer.Context, workflow_id: str) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/workflows/{workflow_id}")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def events(ctx: typer.Context, workflow_id: str) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/workflows/{workflow_id}/events")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def cancel(
    ctx: typer.Context,
    workflow_id: str,
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    client = AiosClient(load_config())
    try:
        response = client.post(f"/api/v1/workflows/{workflow_id}/cancel", json={"reason": reason})
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def retry(workflow_id: str) -> None:
    not_yet_implemented("no retry route exists yet")


@app.command()
def manifest(ctx: typer.Context, workflow_id: str) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/workflows/{workflow_id}/run_manifest")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
