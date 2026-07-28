"""Unit tests for the opaque cursor codec ``GET /api/v1/workflows``
uses (ai_os_kernel.routes.workflows._encode_cursor/_decode_cursor) —
pure functions, no app, no database, no network.
"""

import base64
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from ai_os_kernel.routes.workflows import _decode_cursor, _encode_cursor
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor


def test_a_cursor_round_trips_through_encode_and_decode() -> None:
    cursor = WorkflowListCursor(
        created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC),
        workflow_id="wf_01H0000000000000000000",
    )

    decoded = _decode_cursor(_encode_cursor(cursor))

    assert decoded == cursor


def test_an_encoded_cursor_is_url_safe() -> None:
    cursor = WorkflowListCursor(
        created_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC),
        workflow_id="wf_01H0000000000000000000",
    )

    encoded = _encode_cursor(cursor)

    assert "+" not in encoded
    assert "/" not in encoded


def test_garbage_input_is_rejected_as_an_invalid_cursor() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _decode_cursor("not-a-real-cursor")

    assert exc_info.value.status_code == 400


def test_well_formed_base64_that_is_not_json_is_rejected() -> None:
    encoded = base64.urlsafe_b64encode(b"not json").decode("ascii")

    with pytest.raises(HTTPException) as exc_info:
        _decode_cursor(encoded)

    assert exc_info.value.status_code == 400


def test_valid_json_missing_a_required_field_is_rejected() -> None:
    encoded = base64.urlsafe_b64encode(json.dumps({"workflow_id": "wf_1"}).encode()).decode("ascii")

    with pytest.raises(HTTPException) as exc_info:
        _decode_cursor(encoded)

    assert exc_info.value.status_code == 400
