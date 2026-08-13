"""CLI tests against a real, running Kernel with no real database
(``live_kernel_no_db``) — proves this CLI's own real HTTP-boundary
behaviour: 401/403/503 degrade paths, and the one real success path
(``health live``) that needs no database at all.
"""

from __future__ import annotations

import datetime

import jwt
import pytest
from cli_helpers import invoke

from ai_os_cli.errors import EXIT_AUTHORIZATION_DENIED, EXIT_GENERAL_ERROR

_SIGNING_KEY = "aios-cli-test-signing-key-at-least-32-bytes-long"


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "cli-test-user",
        "roles": roles,
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_health_live_reaches_a_real_running_kernel(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["--output", "json", "health", "live"])
    assert result.exit_code == 0
    assert '"status": "live"' in result.output


def test_health_ready_without_a_real_database_is_a_real_general_error(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["health", "ready"])
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message is not None and "not_ready" in result.error_message


def test_a_missing_bearer_token_against_a_real_kernel_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["pack", "list"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_a_token_lacking_pack_read_against_a_real_kernel_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["nobody"]))

    result = invoke(["pack", "list"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_an_authorized_request_reaches_the_real_capability_manager_unavailable_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    # pack:read is granted only to maintainer/admin (permissions.py's own
    # role table) — viewer/operator/approver do not have it.
    monkeypatch.setenv("AIOS_TOKEN", _token(["maintainer"]))

    result = invoke(["pack", "list"])
    # Authentication and authorization both passed — the failure is the
    # real, honest "no database" degrade, not the security boundary.
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "capability manager is not available"


def test_approve_list_without_a_real_bearer_token_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["approve", "list"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_approve_list_lacking_approval_read_against_a_real_kernel_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    # approval:read is granted only to approver/admin (permissions.py's own
    # role table) — maintainer does not have it.
    monkeypatch.setenv("AIOS_TOKEN", _token(["maintainer"]))

    result = invoke(["approve", "list"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_approve_list_authorized_reaches_the_real_workflow_engine_unavailable_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["approver"]))

    result = invoke(["approve", "list"])
    # Authentication and authorization both passed — the failure is the
    # real, honest "no database" degrade, not the security boundary.
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "workflow engine is not available"


def test_approve_show_authorized_reaches_the_real_workflow_engine_unavailable_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["approver"]))

    result = invoke(["approve", "show", "appr-1"])
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "workflow engine is not available"


def test_workflow_manifest_without_a_real_bearer_token_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["workflow", "manifest", "wf-1"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_workflow_manifest_authorized_reaches_the_real_workflow_engine_unavailable_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    # workflow:read is granted to viewer/operator/approver/admin/maintainer
    # (permissions.py's own role table) — any real role works here.
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["workflow", "manifest", "wf-1"])
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "workflow engine is not available"


def test_workflow_cancel_without_a_real_bearer_token_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["workflow", "cancel", "wf-1", "--yes"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_workflow_cancel_lacking_workflow_control_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    # workflow:control is granted only to operator/maintainer/admin
    # (permissions.py's own role table) — viewer/approver do not have it.
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["workflow", "cancel", "wf-1", "--yes"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_workflow_cancel_authorized_reaches_the_real_workflow_engine_unavailable_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["operator"]))

    result = invoke(["workflow", "cancel", "wf-1", "--yes"])
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "workflow engine is not available"


# --- `aios experiment` (P06-S04-M38-T01, 2026-08-13) -------------------
#
# This group was a deliberate stub until api_architecture.md §6.3 became
# fully real. These prove the four documented subcommands genuinely reach
# the real Kernel routes: the security boundary refuses correctly, and an
# authorized call gets the real "no database" degrade rather than a
# client-side error — the same shape the `approve` tests above establish.


def test_experiment_show_without_a_real_bearer_token_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)

    result = invoke(["experiment", "show", "exp-1"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_experiment_create_lacking_experiment_run_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    # `experiment:run` is granted to operator/maintainer/admin
    # (permissions.py) — `viewer` has the read half only.
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["experiment", "create", "--definition", '{"name": "x"}'])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_experiment_run_lacking_experiment_run_is_a_real_authorization_denial(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["experiment", "run", "exp-1", "--yes"])
    assert result.exit_code == EXIT_AUTHORIZATION_DENIED


def test_experiment_show_authorized_reaches_the_real_evaluation_engine_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["experiment", "show", "exp-1"])
    # Authentication and authorization both passed — the failure is the
    # real, honest "no database" degrade from the route itself.
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "evaluation engine is not available"


def test_experiment_compare_authorized_reaches_the_real_evaluation_engine_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["viewer"]))

    result = invoke(["experiment", "compare", "exp-1"])
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "evaluation engine is not available"


def test_experiment_create_authorized_reaches_the_real_evaluation_engine_degrade(
    live_kernel_no_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_API_URL", live_kernel_no_db)
    monkeypatch.setenv("AIOS_TOKEN", _token(["operator"]))

    result = invoke(
        [
            "experiment",
            "create",
            "--definition",
            '{"name": "n", "description": "d", "definition_id": "se.x", '
            '"definition_version": "1.0.0", "variables": {"model": ["a", "b"]}, '
            '"runs_per_variant": 3}',
        ]
    )
    assert result.exit_code == EXIT_GENERAL_ERROR
    assert result.error_message == "evaluation engine is not available"
