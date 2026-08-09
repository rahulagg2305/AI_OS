"""``aios`` — the CLI entry point (``cli_design.md`` §4's own tree).
Assembles every real and disclosed-not-built command group, resolves
``--output`` once at the root, and converts a real
:class:`~ai_os_cli.errors.CliError` into a real, meaningful process
exit code — never a raw Python traceback for a genuine, expected
failure (a 404, a timeout, a bad decision value).

**Why this catch lives here, not inside Click/Typer's own exception
handling:** investigated using ``click.ClickException`` for this
(Click's own ``main()`` catches that class specifically) and found it
does not work — Typer (0.27.1, installed here) vendors its own
private, separate copy of Click (``typer._click``), whose
``ClickException`` is a genuinely different class object; an instance
of the public ``click.exceptions.ClickException`` never matches
Typer's internal ``isinstance`` check against its own vendored one.
See :mod:`ai_os_cli.errors`'s own module docstring for the full
finding. A plain ``except CliError`` here, verified working by direct
smoke test, is the real fix.
"""

from __future__ import annotations

import sys

import typer

from ai_os_cli.commands import approve, auth, config_cmd, experiment, health, logs, pack, workflow
from ai_os_cli.errors import CliError
from ai_os_cli.output import resolve_output_format

app = typer.Typer(
    help="aios — scriptable access to the AI_OS Kernel API.",
    pretty_exceptions_enable=False,
)
app.add_typer(auth.app, name="auth")
app.add_typer(workflow.app, name="workflow")
app.add_typer(approve.app, name="approve")
app.add_typer(experiment.app, name="experiment")
app.add_typer(pack.app, name="pack")
app.add_typer(config_cmd.app, name="config")
app.add_typer(health.app, name="health")
app.add_typer(logs.app, name="logs")


@app.callback()
def main(
    ctx: typer.Context,
    output: str | None = typer.Option(
        None, "--output", help="'human' (Rich) or 'json'. Defaults per cli_design.md §4."
    ),
) -> None:
    ctx.obj = {"output_format": resolve_output_format(output)}


def run() -> None:
    """The real ``[project.scripts]`` entry point. Uses ``sys.exit``,
    not ``typer.Exit`` — ``CliError`` is caught here, outside Click's
    own invocation loop (the one place ``typer.Exit`` is handled
    specially), so re-raising ``typer.Exit`` from here would itself
    become an unhandled exception with a real exit code but an ugly,
    misleading traceback (verified by direct smoke test)."""
    try:
        app()
    except CliError as exc:
        typer.echo(exc.message, err=True)
        sys.exit(exc.exit_code)


if __name__ == "__main__":
    run()
