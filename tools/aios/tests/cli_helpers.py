"""A thin ``CliRunner`` wrapper matching how this CLI's own real
entry point (:func:`ai_os_cli.main.run`) actually behaves.

``typer.testing.CliRunner.invoke`` calls the Typer ``app`` directly,
bypassing ``run()``'s own ``except CliError`` — so a real
:class:`~ai_os_cli.errors.CliError` surfaces as ``result.exception``
here, not as ``result.exit_code``. This helper does the same
translation ``run()`` does, so a test asserts against the real
production exit code, not CliRunner's own generic "any uncaught
exception is exit code 1" default.
"""

from __future__ import annotations

from dataclasses import dataclass

from typer.testing import CliRunner

from ai_os_cli.errors import CliError
from ai_os_cli.main import app

_runner = CliRunner()


@dataclass(frozen=True)
class InvokeResult:
    exit_code: int
    output: str
    error_message: str | None


def invoke(args: list[str]) -> InvokeResult:
    result = _runner.invoke(app, args)
    if isinstance(result.exception, CliError):
        return InvokeResult(
            exit_code=result.exception.exit_code,
            output=result.output,
            error_message=result.exception.message,
        )
    return InvokeResult(exit_code=result.exit_code, output=result.output, error_message=None)
