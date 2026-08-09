"""Real, meaningful exit codes (``cli_design.md`` §4's own table) —
driven by the actual HTTP response a command received, never guessed
or defaulted to a bare ``1`` for everything.

::

    0  success
    1  general error       (any response/failure not covered below)
    2  usage error         (a malformed request body the Kernel itself rejected, 422)
    3  authorization denied (401 unauthenticated, 403 forbidden)
    4  resource not found  (404)
    5  operation failed a gate (409 — a real state conflict: an
       already-decided approval, an invalid pack transition, etc.)
    6  timeout

Typer/Click already exit ``2`` on its own for a genuine CLI usage
error (a missing required option, an unparseable value) — this module
covers only the Kernel-response half of the table.

**Not a :class:`click.ClickException`, on purpose, after investigating
it as the more idiomatic-looking option:** Typer (0.27.1, installed
here) vendors its own private, separate copy of Click
(``typer._click``), and ``typer._click.exceptions.ClickException`` is
a genuinely different class object from the public ``click.exceptions.
ClickException`` — Typer's own internal ``isinstance`` check against
its vendored copy never matches an instance of the public one, so
subclassing the public class silently does not get Click/Typer's own
automatic handling at all. A plain ``Exception`` subclass, caught
explicitly by :func:`ai_os_cli.main.run` (production) and this
package's own ``tests/cli_helpers.py`` (tests) — the same real
behaviour, asserted directly, not assumed from vendored internals.
"""

from __future__ import annotations

import httpx

EXIT_GENERAL_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_AUTHORIZATION_DENIED = 3
EXIT_NOT_FOUND = 4
EXIT_GATE_FAILED = 5
EXIT_TIMEOUT = 6

_STATUS_TO_EXIT_CODE = {
    401: EXIT_AUTHORIZATION_DENIED,
    403: EXIT_AUTHORIZATION_DENIED,
    404: EXIT_NOT_FOUND,
    409: EXIT_GATE_FAILED,
    422: EXIT_USAGE_ERROR,
}


class CliError(Exception):
    """Raised by a command to fail with a real, specific exit code —
    never a bare ``sys.exit(1)`` that discards which real condition
    actually occurred."""

    def __init__(self, message: str, *, exit_code: int = EXIT_GENERAL_ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def exit_code_for_status(status_code: int) -> int:
    """The real exit code for a genuine HTTP response — every status
    this table does not name falls back to the real "general error"
    bucket, not a fabricated, more specific one."""
    return _STATUS_TO_EXIT_CODE.get(status_code, EXIT_GENERAL_ERROR)


def raise_for_response(response: httpx.Response) -> None:
    """Raises a real :class:`CliError` for any non-2xx response, with
    the real detail the Kernel's own RFC 9457 problem+json body
    carries (``problem_details.py``) when present, falling back to the
    raw body otherwise — never a fabricated "something went wrong"."""
    if response.is_success:
        return
    detail = _extract_detail(response)
    raise CliError(detail, exit_code=exit_code_for_status(response.status_code))


def _extract_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        for key in ("detail", "title"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    return response.text or f"HTTP {response.status_code}"
