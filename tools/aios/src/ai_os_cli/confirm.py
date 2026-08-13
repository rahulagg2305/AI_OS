"""One real, shared confirmation gate for the CLI's destructive
commands — ``cli_design.md`` §4's own conventions table ("Destructive
commands | Require ``--yes`` or an interactive confirmation") and §5
("Destructive or high-impact commands should require explicit
confirmation").

**The convention was documented from the start and implemented
nowhere** until 2026-08-13. It was found while building
``aios experiment run``, which synchronously executes one real workflow
per variant × replicate — every one of them a real, billable LLM call —
with no prompt at all. Implementing it for that one command would have
made the rule arbitrary, so the whole set was resolved at once.

**Which commands are gated was a product-owner decision, not a
derivation.** What the codebase *does* settle is that exactly eight
commands mutate server state (POST/PATCH); which of those count as
"destructive or high-impact" is a judgement about users, so the options
were put to the product owner. The chosen line is **irreversible or
costly**:

- ``workflow cancel`` — a one-way terminal transition
- ``pack deactivate`` — removes a live capability from the platform
- ``approve decide`` — guarded against double-decide, so a wrong
  decision is permanent, and governance-critical under R-001
- ``experiment run`` — spends real money, synchronously

The four mutating commands deliberately left unprompted are
``workflow start``, ``experiment create``, ``pack activate`` and
``config set`` — additive or creative verbs, the same line kubectl,
terraform and gh draw between destroy and create. **One disclosed
consequence:** ``workflow start`` triggers real agents making real LLM
calls, so a money-spending path remains unprompted. That was explicit in
the decision, not overlooked.

**Non-interactive use must fail, never hang.** This CLI exists to
compose in scripts (``cli_design.md`` §4: "so it composes in scripts
rather than only reading well"). Prompting on a pipe or in CI would
block forever on a stdin that never answers, so a non-TTY without
``--yes`` is a real usage error with the documented exit code 2 — a
clear, immediate, scriptable failure that names the flag to pass.
"""

from __future__ import annotations

import sys

import typer

from ai_os_cli.errors import EXIT_GENERAL_ERROR, EXIT_USAGE_ERROR, CliError


def require_confirmation(action: str, *, yes: bool) -> None:
    """Gate a destructive command on explicit consent.

    ``action`` is a real, specific description of what is about to
    happen — it is shown to the user, so "cancel workflow wf_123" is
    right and "proceed" is not.
    """
    if yes:
        return

    if not sys.stdin.isatty():
        raise CliError(
            f"{action} needs confirmation, and stdin is not a terminal — pass --yes",
            exit_code=EXIT_USAGE_ERROR,
        )

    if not typer.confirm(f"{action}. Continue?"):
        # A deliberate decline is not success: a script chaining on `&&`
        # must not proceed as though the action happened.
        raise CliError("aborted", exit_code=EXIT_GENERAL_ERROR)
