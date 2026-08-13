"""``aios experiment`` — ``create``/``run``/``show``/``compare``
(``cli_design.md`` §4), all real as of ``P06-S04-M38-T01``'s 2026-08-13
increment.

**The blocker this group was stubbed with is gone.** Every subcommand
here previously failed with "no ``/api/v1/experiments`` route exists in
production yet", and ``cli_design.md`` §3 recorded the group as blocked
on "Benchmarking Pack still 0% built". Both statements have since become
false: api_architecture.md §6.3 is fully real —
``POST /experiments`` (``P04-S01-M12-T12``),
``POST /experiments/{id}/run`` (``T13``),
``GET /experiments/{id}/comparison`` (``T14``) and the reads alongside
them — so the four documented subcommands map onto four real, tested
routes with no new Kernel work at all.

**Exactly the four subcommands ``cli_design.md`` §4's own command tree
names, and no more.** ``GET /api/v1/experiments`` (list) is real and
would be trivial to expose, but the documented tree is
``create · run · show · compare``; adding an undocumented fifth command
would be inventing CLI surface, the same discipline that kept
``GET /usage/cost`` unbuilt when its capability already existed
elsewhere.

**``--definition`` takes JSON, matching ``workflow start --inputs``.**
The create body is a structured object (``variables`` is itself a
mapping of lists), so it cannot be flattened into flags without
inventing a taxonomy no document describes. A shell can supply a file
with ``--definition "$(cat experiment.json)"``; a dedicated
``--definition-file`` flag would be a second convention this CLI does
not have anywhere else.

**No ``--yes`` on ``run``, deliberately, and this is disclosed rather
than quietly skipped.** ``cli_design.md`` §4's conventions table says
destructive or high-impact commands should require confirmation — and
``run`` genuinely is high-impact: it synchronously executes one real
workflow per variant × replicate, each making real, billable LLM calls.
But **no command in this CLI implements ``--yes`` today**, including
``workflow cancel`` and ``pack deactivate``, which are at least as
destructive. Implementing it here alone would make the convention
arbitrary — a user would learn that ``run`` needs confirmation while
cancelling a workflow does not. The gap is CLI-wide and is recorded as
such (``P06-S04-M38-T01``); the cost is instead made explicit in this
command's own help text, so nobody runs it unaware.
"""

from __future__ import annotations

import json

import typer

from ai_os_cli.client import AiosClient
from ai_os_cli.config import load_config
from ai_os_cli.confirm import require_confirmation
from ai_os_cli.errors import EXIT_USAGE_ERROR, CliError
from ai_os_cli.output import render

app = typer.Typer(help="Trigger or inspect experiments.")


@app.command()
def create(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        help=(
            "A JSON object: name, description, definition_id, definition_version, "
            'variables, runs_per_variant. Use --definition "$(cat experiment.json)" '
            "to supply it from a file."
        ),
    ),
) -> None:
    """Define a new experiment (`POST /api/v1/experiments`)."""
    try:
        parsed_definition = json.loads(definition)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"--definition is not valid JSON: {exc}", exit_code=EXIT_USAGE_ERROR
        ) from exc

    client = AiosClient(load_config())
    try:
        response = client.post("/api/v1/experiments", json=parsed_definition)
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def run(
    ctx: typer.Context,
    experiment_id: str,
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Run a defined experiment (`POST /api/v1/experiments/{id}/run`).

    Runs synchronously and costs real money: one real workflow per
    variant x replicate, each making real, billable LLM calls — which is
    why this is one of the four commands `cli_design.md` §4's own
    convention gates behind a confirmation.
    """
    require_confirmation(
        f"Run experiment '{experiment_id}' — this executes real workflows "
        "and makes real, billable LLM calls",
        yes=yes,
    )
    client = AiosClient(load_config())
    try:
        response = client.post(f"/api/v1/experiments/{experiment_id}/run")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def show(ctx: typer.Context, experiment_id: str) -> None:
    """Show one experiment (`GET /api/v1/experiments/{id}`)."""
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/experiments/{experiment_id}")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])


@app.command()
def compare(ctx: typer.Context, experiment_id: str) -> None:
    """Compare an experiment's variants
    (`GET /api/v1/experiments/{id}/comparison`).

    Returns the real per-variant, per-metric aggregation
    `SqlComparisonComputer` computes over the experiment's own recorded
    runs — an experiment that exists but has never run is a real, valid,
    empty result, not an error.
    """
    client = AiosClient(load_config())
    try:
        response = client.get(f"/api/v1/experiments/{experiment_id}/comparison")
    finally:
        client.close()
    render(response.json(), output_format=ctx.obj["output_format"])
