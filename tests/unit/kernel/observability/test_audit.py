"""Unit tests for the pure hashing/verification logic in
:mod:`ai_os_kernel.observability.audit` — no database. The real,
Postgres-backed writer proof lives in
``tests/integration/observability/test_audit_log.py``.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from ai_os_kernel.observability.audit import (
    AuditLogRecord,
    AuditOutcome,
    compute_row_hash,
    verify_chain,
)

_WHEN = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def _record(
    *,
    seq: int,
    audit_id: str,
    prev_hash: str | None,
    row_hash: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLogRecord:
    detail = detail if detail is not None else {"n": seq}
    computed = compute_row_hash(
        audit_id=audit_id,
        event_type="test.event",
        principal_id="user-1",
        principal_type="user",
        resource_type=None,
        resource_id=None,
        outcome=AuditOutcome.SUCCESS,
        detail=detail,
        trace_id=None,
        occurred_at=_WHEN,
        prev_hash=prev_hash,
    )
    return AuditLogRecord(
        audit_id=audit_id,
        seq=seq,
        event_type="test.event",
        principal_id="user-1",
        principal_type="user",
        resource_type=None,
        resource_id=None,
        outcome=AuditOutcome.SUCCESS,
        detail=detail,
        trace_id=None,
        prev_hash=prev_hash,
        row_hash=row_hash if row_hash is not None else computed,
        occurred_at=_WHEN,
    )


def _hash(
    *,
    audit_id: str = "aud_1",
    event_type: str = "auth.success",
    principal_id: str = "user-1",
    principal_type: str = "user",
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = AuditOutcome.SUCCESS,
    detail: dict[str, Any] | None = None,
    trace_id: str | None = None,
    occurred_at: datetime = _WHEN,
    prev_hash: str | None = None,
) -> str:
    return compute_row_hash(
        audit_id=audit_id,
        event_type=event_type,
        principal_id=principal_id,
        principal_type=principal_type,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail if detail is not None else {},
        trace_id=trace_id,
        occurred_at=occurred_at,
        prev_hash=prev_hash,
    )


def test_compute_row_hash_is_deterministic() -> None:
    assert _hash(detail={"b": 2, "a": 1}) == _hash(detail={"b": 2, "a": 1})


def test_compute_row_hash_is_a_real_sha256_hex_digest() -> None:
    digest = compute_row_hash(
        audit_id="aud_1",
        event_type="auth.success",
        principal_id="user-1",
        principal_type="user",
        resource_type=None,
        resource_id=None,
        outcome=AuditOutcome.SUCCESS,
        detail={},
        trace_id=None,
        occurred_at=_WHEN,
        prev_hash=None,
    )
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_changing_any_hashed_field_changes_the_hash() -> None:
    original = _hash(detail={"k": "v"})

    assert _hash(detail={"k": "different"}) != original
    assert _hash(detail={"k": "v"}, outcome=AuditOutcome.FAILURE) != original
    assert _hash(detail={"k": "v"}, principal_id="user-2") != original
    assert _hash(detail={"k": "v"}, prev_hash="0" * 64) != original


def test_the_hash_is_normalized_across_time_zone_representations() -> None:
    """The same real instant, read back with a different UTC offset
    representation, must still hash identically — this is exactly what
    a differing Postgres session time zone could otherwise produce for
    a row nobody tampered with."""
    from datetime import timedelta, timezone

    same_instant_other_offset = _WHEN.astimezone(timezone(timedelta(hours=5)))

    assert _hash(occurred_at=_WHEN) == _hash(occurred_at=same_instant_other_offset)


def test_verify_chain_accepts_an_empty_chain() -> None:
    assert verify_chain([]).valid is True


def test_verify_chain_accepts_a_single_genesis_row() -> None:
    result = verify_chain([_record(seq=1, audit_id="aud_1", prev_hash=None)])
    assert result.valid is True


def test_verify_chain_accepts_a_real_multi_row_chain() -> None:
    r1 = _record(seq=1, audit_id="aud_1", prev_hash=None)
    r2 = _record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash)
    r3 = _record(seq=3, audit_id="aud_3", prev_hash=r2.row_hash)

    result = verify_chain([r1, r2, r3])

    assert result.valid is True
    assert result.broken_at_seq is None


def test_verify_chain_does_not_require_records_pre_sorted() -> None:
    r1 = _record(seq=1, audit_id="aud_1", prev_hash=None)
    r2 = _record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash)

    assert verify_chain([r2, r1]).valid is True


def test_verify_chain_rejects_a_genesis_row_with_a_non_null_prev_hash() -> None:
    result = verify_chain([_record(seq=1, audit_id="aud_1", prev_hash="0" * 64)])

    assert result.valid is False
    assert result.broken_at_seq == 1
    assert result.reason is not None and "prev_hash does not match" in result.reason


def test_verify_chain_detects_content_tampered_after_hashing() -> None:
    """The `row_hash` is computed for the *original* detail, then the
    record is rebuilt with different detail but the same (now stale)
    row_hash — exactly what a direct-SQL edit that never touches
    row_hash produces."""
    genuine = _record(seq=1, audit_id="aud_1", prev_hash=None)
    tampered = genuine.model_copy(update={"detail": {"n": "not the original value"}})

    result = verify_chain([tampered])

    assert result.valid is False
    assert result.broken_at_seq == 1
    assert result.reason is not None
    assert "row_hash does not match" in result.reason
    assert "aud_1" in result.reason


def test_verify_chain_detects_a_forged_prev_hash_pointer() -> None:
    r1 = _record(seq=1, audit_id="aud_1", prev_hash=None)
    r2_genuine = _record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash)
    r2_forged = r2_genuine.model_copy(update={"prev_hash": "f" * 64})

    result = verify_chain([r1, r2_forged])

    assert result.valid is False
    assert result.broken_at_seq == 2


@pytest.mark.parametrize("outcome", list(AuditOutcome))
def test_every_documented_outcome_value_is_a_real_enum_member(outcome: AuditOutcome) -> None:
    """AuditOutcome mirrors governance_schema.py's own CHECK constraint
    list exactly — a typo here would otherwise surface only as a raw
    database constraint violation."""
    assert outcome in ("allowed", "denied", "success", "failure")
