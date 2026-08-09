"""``aios approve`` — ``decide`` (``cli_design.md`` §4). ``list``/``show``
are declared but not built: ``ApprovalRepository`` has no method that
lists approvals at all — the identical, already-disclosed gap
Dashboard's own ``P06-S03-M39-T02`` report named for its Pending
Approvals view. There is no way, at the query layer or the HTTP layer,
to fetch "all pending approvals" today."""

from __future__ import annotations

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.errors import EXIT_USAGE_ERROR, CliError
from ai_os_cli.not_built import not_yet_implemented
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
def list_approvals() -> None:
    not_yet_implemented("ApprovalRepository has no method that lists approvals")


@app.command()
def show(approval_id: str) -> None:
    not_yet_implemented("no get-approval-by-id route exists")
