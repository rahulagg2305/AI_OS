"""CLI tests needing no server at all: ``auth`` (100% local),
disclosed not-built commands, and local usage-error validation that
fails before any HTTP call is ever made."""

from __future__ import annotations

import jwt
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
    for args in (
        ["experiment", "create"],
        ["experiment", "run", "exp-1"],
        ["experiment", "show", "exp-1"],
        ["experiment", "compare", "exp-1"],
        ["logs", "tail"],
        ["logs", "search", "query"],
        ["workflow", "cancel", "wf-1"],
        ["workflow", "retry", "wf-1"],
        ["workflow", "manifest", "wf-1"],
        ["approve", "list"],
        ["approve", "show", "appr-1"],
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
