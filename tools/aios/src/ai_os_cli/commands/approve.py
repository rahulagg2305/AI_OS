"""``aios approve`` — ``decide``/``list``/``show`` (``cli_design.md``
§4), all real. ``list``/``show`` were disclosed as blocked at
``P06-S04-M38-T01`` ("``ApprovalRepository`` has no method that lists
approvals at all") — that gap closed at ``P06-S03-M39-T02``
(Dashboard's own Pending Approvals view: ``list_pending()``/
``GET /api/v1/approvals``), and this step adds the one further real
route (``GET /api/v1/approvals/{approval_id}``) ``show`` needs, over
the same, already-existing ``SqlApprovalRepository.get_by_id`` read."""

from __future__ import annotations

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.errors import EXIT_USAGE_ERROR, CliError
from ai_os_cli.output import render

app = typer.Typer(help="Decide Human Approval Points.")

_VALID_DECISIONS = {"approved", "rejected"}


@app.command()
def decide(
    ctx: typer.Context,
    workflow_id: str,
    approval_id: str,
    decision: str,
    comment: str | None = typer.Option(None, "--comment"),
) -> None:
    if decision not in _VALID_DECISIONS:
        raise CliError(
            f"decision must be one of {sorted(_VALID_DECISIONS)}, got '{decision}'",
            exit_code=EXIT_USAGE_ERROR,
        )

    client = AiosClient(load_config())
    try:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions",
            json={"decision": decision, "comment": comment},
        )
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command(name="list")
def list_approvals(ctx: typer.Context) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get("/api/v1/approvals")
    finally:
        client.close()
    render(response.json()["approvals"], output_format=ctx.obj["output_format"])


@app.command()
def show(ctx: typer.Context, approval_id: str) -> None:
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/approvals/{approval_id}")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
