"""Unit tests for the LLM Gateway's Error Taxonomy
(ai_os_kernel.llm_gateway.error_taxonomy): pure classification, no
network, no I/O.
"""

import pytest

from ai_os_kernel.llm_gateway.error_taxonomy import (
    ErrorCategory,
    classify_http_status,
    parse_retry_after_seconds,
)


@pytest.mark.parametrize(
    ("status_code", "expected_category", "expected_error_code", "expected_retriable"),
    [
        # Exactly llm_gateway.md §10's own documented table.
        (400, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (401, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
        (403, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
        (429, ErrorCategory.TRANSIENT, "llm.rate_limited", True),
        (529, ErrorCategory.TRANSIENT, "llm.overloaded", True),
        (500, ErrorCategory.TRANSIENT, "llm.provider_error", True),
        (502, ErrorCategory.TRANSIENT, "llm.provider_error", True),
        (503, ErrorCategory.TRANSIENT, "llm.provider_error", True),
        # Undocumented codes fall back to a safe default by range.
        (404, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (409, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (422, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (599, ErrorCategory.TRANSIENT, "llm.provider_error", True),
    ],
)
def test_classify_http_status(
    status_code: int,
    expected_category: ErrorCategory,
    expected_error_code: str,
    expected_retriable: bool,
) -> None:
    classification = classify_http_status(status_code)

    assert classification.category == expected_category
    assert classification.error_code == expected_error_code
    assert classification.retriable is expected_retriable


def test_parse_retry_after_seconds_reads_the_numeric_form() -> None:
    assert parse_retry_after_seconds("7") == 7.0
    assert parse_retry_after_seconds("2.5") == 2.5


def test_parse_retry_after_seconds_returns_none_for_a_missing_header() -> None:
    assert parse_retry_after_seconds(None) is None


def test_parse_retry_after_seconds_returns_none_for_the_http_date_form() -> None:
    # A real, documented gap — see this module's own docstring — not a
    # crash.
    assert parse_retry_after_seconds("Wed, 21 Oct 2026 07:28:00 GMT") is None
