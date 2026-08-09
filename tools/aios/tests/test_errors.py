"""Unit tests for ``ai_os_cli.errors`` — the real, documented exit-code
table (``cli_design.md`` §4), pure logic, no server."""

from __future__ import annotations

import httpx
import pytest

from ai_os_cli.errors import (
    EXIT_AUTHORIZATION_DENIED,
    EXIT_GATE_FAILED,
    EXIT_GENERAL_ERROR,
    EXIT_NOT_FOUND,
    EXIT_USAGE_ERROR,
    CliError,
    exit_code_for_status,
    raise_for_response,
)


@pytest.mark.parametrize(
    ("status_code", "expected_exit_code"),
    [
        (401, EXIT_AUTHORIZATION_DENIED),
        (403, EXIT_AUTHORIZATION_DENIED),
        (404, EXIT_NOT_FOUND),
        (409, EXIT_GATE_FAILED),
        (422, EXIT_USAGE_ERROR),
        (500, EXIT_GENERAL_ERROR),
        (503, EXIT_GENERAL_ERROR),
    ],
)
def test_every_real_documented_status_maps_to_its_real_exit_code(
    status_code: int, expected_exit_code: int
) -> None:
    assert exit_code_for_status(status_code) == expected_exit_code


def test_a_successful_response_never_raises() -> None:
    response = httpx.Response(200, json={"status": "ok"})
    raise_for_response(response)  # must not raise


def test_a_problem_json_body_s_own_detail_becomes_the_real_message() -> None:
    response = httpx.Response(404, json={"detail": "no workflow instance with id 'wf-1'"})
    with pytest.raises(CliError) as excinfo:
        raise_for_response(response)
    assert excinfo.value.message == "no workflow instance with id 'wf-1'"
    assert excinfo.value.exit_code == EXIT_NOT_FOUND


def test_a_body_with_no_detail_or_title_falls_back_to_the_real_raw_text() -> None:
    response = httpx.Response(500, text="internal error")
    with pytest.raises(CliError) as excinfo:
        raise_for_response(response)
    assert excinfo.value.message == "internal error"
    assert excinfo.value.exit_code == EXIT_GENERAL_ERROR
