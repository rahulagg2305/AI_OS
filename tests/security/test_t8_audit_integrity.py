"""T8 — Audit log tampering (security_architecture.md §4/§12). Real
defense exercised here: the hash-chained ``governance.audit_log`` —
:func:`~ai_os_kernel.observability.audit.verify_chain` recomputes every
row's real SHA-256 hash and confirms every ``prev_hash`` genuinely
matches the previous row's real ``row_hash``, not merely what that row's
own column claims.

The attempt: an actor with raw database access (the real, credible
threat this control exists for — SQL bypasses the ``SqlAuditLogWriter``
API entirely) directly edits a stored row's content, and separately
splices in a forged row with a fabricated ``prev_hash`` pointer. Both are
genuine tamper attempts on the real records; ``verify_chain`` must
genuinely catch both.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ai_os_kernel.observability.audit import (
    AuditLogRecord,
    AuditOutcome,
    compute_row_hash,
    verify_chain,
)

_WHEN = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def _genuine_record(
    *, seq: int, audit_id: str, prev_hash: str | None, detail: dict[str, Any]
) -> AuditLogRecord:
    row_hash = compute_row_hash(
        audit_id=audit_id,
        event_type="secret.access.allowed",
        principal_id="admin-1",
        principal_type="user",
        resource_type="secret",
        resource_id="secret://env/llm-api-key",
        outcome=AuditOutcome.ALLOWED,
        detail=detail,
        trace_id=None,
        occurred_at=_WHEN,
        prev_hash=prev_hash,
    )
    return AuditLogRecord(
        audit_id=audit_id,
        seq=seq,
        event_type="secret.access.allowed",
        principal_id="admin-1",
        principal_type="user",
        resource_type="secret",
        resource_id="secret://env/llm-api-key",
        outcome=AuditOutcome.ALLOWED,
        detail=detail,
        trace_id=None,
        prev_hash=prev_hash,
        row_hash=row_hash,
        occurred_at=_WHEN,
    )


def test_a_real_chain_of_genuine_untampered_rows_verifies_clean() -> None:
    """Proportionality check: a real, unmodified chain must pass."""
    r1 = _genuine_record(seq=1, audit_id="aud_1", prev_hash=None, detail={"n": 1})
    r2 = _genuine_record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash, detail={"n": 2})
    r3 = _genuine_record(seq=3, audit_id="aud_3", prev_hash=r2.row_hash, detail={"n": 3})

    result = verify_chain([r1, r2, r3])

    assert result.valid is True


def test_a_real_tamper_attempt_via_direct_row_edit_bypassing_the_writer_is_detected() -> None:
    """The credible real threat: an actor with raw database access edits
    a row's `detail` directly (e.g. rewriting an audit trail after a
    security incident to hide what was accessed), never going through
    `SqlAuditLogWriter.record` and therefore never recomputing `row_hash`
    to match the new content."""
    genuine = _genuine_record(
        seq=1, audit_id="aud_1", prev_hash=None, detail={"resource": "secret://env/llm-api-key"}
    )
    tampered = genuine.model_copy(update={"detail": {"resource": "secret://env/nothing-happened"}})

    result = verify_chain([tampered])

    assert result.valid is False
    assert result.broken_at_seq == 1
    assert result.reason is not None and "aud_1" in result.reason


def test_a_real_tamper_attempt_splicing_in_a_forged_row_with_a_fake_prev_hash_is_detected() -> None:
    """A second, distinct tamper shape: an actor deletes a genuine row
    and inserts a forged replacement, computing a self-consistent
    `row_hash` for the forged content but unable to know what the real
    next row's `prev_hash` should have pointed to without also rewriting
    every row after it."""
    r1 = _genuine_record(seq=1, audit_id="aud_1", prev_hash=None, detail={"n": 1})
    r2_genuine = _genuine_record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash, detail={"n": 2})
    r2_forged = r2_genuine.model_copy(update={"prev_hash": "f" * 64})

    result = verify_chain([r1, r2_forged])

    assert result.valid is False
    assert result.broken_at_seq == 2
