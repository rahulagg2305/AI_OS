"""CLI tests needing no server at all: ``auth`` (100% local),
disclosed not-built commands, and local usage-error validation that
fails before any HTTP call is ever made."""

from __future__ import annotations

import jwt
import pytest
from cli_helpers import invoke

from ai_os_cli.errors import EXIT_GENERAL_ERROR, EXIT_USAGE_ERROR

_SIGNING_KEY = "does-not-matter-this-cli-never-verifies-it"


def test_login_then_whoami_round_trips_a_real_tokens_own_claims() -> None:
    token = jwt.encode({"sub": "alice", "roles": ["admin"]}, _SIGNING_KEY, algorithm="HS256")

    login_result = invoke(["auth", "login", "--token", token])
    assert login_result.exit_code == 0

    whoami_result = invoke(["--output", "json", "auth", "whoami"])
    assert whoami_result.exit_code == 0
    assert '"sub": "alice"' in whoami_result.output
    assert '"admin"' in whoami_result.output


def test_whoami_without_a_stored_token_is_a_real_authorization_denial() -> None:
    result = invoke(["auth", "whoami"])
    assert result.error_message == "not logged in — run 'aios auth login'"


def test_logout_then_whoami_is_a_real_authorization_denial() -> None:
    token = jwt.encode({"sub": "bob"}, _SIGNING_KEY, algorithm="HS256")
    invoke(["auth", "login", "--token", token])

    invoke(["auth", "logout"])
    result = invoke(["auth", "whoami"])
    assert result.error_message == "not logged in — run 'aios auth login'"


def test_every_documented_but_not_built_command_fails_clearly_not_silently() -> None:
    """The `experiment` group left this list on 2026-08-13
    (`P06-S04-M38-T01`): its stated blocker — "no /api/v1/experiments
    route exists in production" — stopped being true once
    api_architecture.md §6.3 became fully real, so all four subcommands
    are now genuinely built and covered by their own tests below and in
    `test_cli_live.py`. What remains here is genuinely blocked:
    `logs` has no query route at all, and `workflow retry` is blocked by
    R-016 (no production code ever persists a workflow as `failed`)."""
    for args in (
        ["logs", "tail"],
        ["logs", "search", "query"],
        ["workflow", "retry", "wf-1"],
    ):
        result = invoke(args)
        assert result.exit_code == EXIT_GENERAL_ERROR, f"{args} did not exit 1"
        assert result.error_message is not None and result.error_message.startswith(
            "not yet implemented:"
        ), f"{args} gave no real reason"


def test_a_malformed_workflow_start_input_is_a_real_usage_error() -> None:
    result = invoke(["workflow", "start", "--inputs", "not-json"])
    assert result.exit_code == EXIT_USAGE_ERROR
    assert result.error_message is not None and "not valid JSON" in result.error_message


def test_an_invalid_decision_value_is_a_real_usage_error() -> None:
    result = invoke(["approve", "decide", "wf-1", "appr-1", "maybe"])
    assert result.exit_code == EXIT_USAGE_ERROR
    assert result.error_message is not None and "approved" in result.error_message


def test_a_malformed_experiment_definition_is_a_real_usage_error() -> None:
    """`experiment create` parses `--definition` as JSON before any
    network call, the identical shape `workflow start --inputs` uses —
    so a typo is a usage error (exit 2), never a confusing request
    failure against the Kernel."""
    result = invoke(["experiment", "create", "--definition", "not-json"])
    assert result.exit_code == EXIT_USAGE_ERROR
    assert result.error_message is not None and "not valid JSON" in result.error_message


def test_every_documented_experiment_subcommand_is_discoverable() -> None:
    """`cli_design.md` §4's command tree names exactly four subcommands
    for this group — and deliberately no `list`, even though
    `GET /api/v1/experiments` is real, because adding an undocumented
    command would be inventing CLI surface."""
    result = invoke(["experiment", "--help"])
    assert result.exit_code == 0
    for subcommand in ("create", "run", "show", "compare"):
        assert subcommand in result.output, f"'{subcommand}' is not discoverable"
    assert "list" not in result.output.split("Commands")[-1]


# --- The `--yes` confirmation gate (P06-S04-M38-T01, 2026-08-13) -------
#
# `cli_design.md` §4's conventions table required this from the start and
# nothing implemented it, which was found when `experiment run` shipped
# able to spend real money with no prompt. Which commands are gated was a
# product-owner decision (irreversible or costly); these prove the gate
# itself, not the choice.


@pytest.mark.parametrize(
    "args",
    [
        ["workflow", "cancel", "wf-1"],
        ["pack", "deactivate", "pack-1", "--reason", "r"],
        ["approve", "decide", "wf-1", "appr-1", "approved"],
        ["experiment", "run", "exp-1"],
    ],
)
def test_a_destructive_command_without_yes_refuses_rather_than_hanging(
    args: list[str],
) -> None:
    """The scriptability requirement, proven rather than assumed: pytest
    runs with a non-TTY stdin, so a prompt here would block forever. Each
    gated command must instead fail immediately with the documented usage
    exit code and name the flag to pass.

    This test would hang, not fail, if `require_confirmation` ever called
    `typer.confirm` unconditionally — which is exactly the regression it
    exists to catch.
    """
    result = invoke(args)
    assert result.exit_code == EXIT_USAGE_ERROR, f"{args} did not refuse"
    assert result.error_message is not None
    assert "--yes" in result.error_message, f"{args} did not name the flag to pass"


@pytest.mark.parametrize(
    "args",
    [
        ["workflow", "cancel", "wf-1", "--yes"],
        ["pack", "deactivate", "pack-1", "--reason", "r", "--yes"],
        ["approve", "decide", "wf-1", "appr-1", "approved", "--yes"],
        ["experiment", "run", "exp-1", "--yes"],
    ],
)
def test_yes_bypasses_the_gate_and_the_command_proceeds(args: list[str]) -> None:
    """With `--yes` the gate is passed and the command genuinely runs —
    reaching a real connection failure against a Kernel that is not
    running here, never the usage error the gate produces. Proving the
    flag *works* matters as much as proving the gate blocks: a gate that
    could not be bypassed would break every script."""
    result = invoke(args)
    assert result.exit_code != EXIT_USAGE_ERROR, f"{args} was still blocked by the gate"


def test_an_invalid_decision_is_rejected_before_the_confirmation_prompt() -> None:
    """Ordering matters: a usage error must surface immediately, not
    after asking the operator to confirm something the CLI was always
    going to refuse."""
    result = invoke(["approve", "decide", "wf-1", "appr-1", "maybe"])
    assert result.error_message is not None and "approved" in result.error_message
