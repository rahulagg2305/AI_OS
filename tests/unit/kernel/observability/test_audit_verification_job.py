"""Unit tests for the scheduled audit-chain verification job
(``P01-S05-M04-T06``). The hash-chain logic itself
(:func:`~ai_os_kernel.observability.audit.verify_chain`) is already
proven by ``test_audit.py`` and the real-Postgres integration tests in
``tests/integration/observability/test_audit_log.py`` — these tests
prove only the job's own new behaviour: it runs on a real interval, and
it alerts (an ERROR-level structured log) the instant the chain it
reads is broken.
"""

import asyncio
from datetime import UTC, datetime

import structlog.testing

from ai_os_kernel.observability.audit import AuditLogRecord, AuditOutcome, compute_row_hash
from ai_os_kernel.observability.audit_verification_job import (
    run_audit_chain_verification_once,
    run_periodic_audit_chain_verification,
)

_WHEN = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def _record(*, seq: int, audit_id: str, prev_hash: str | None) -> AuditLogRecord:
    detail = {"n": seq}
    row_hash = compute_row_hash(
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
        row_hash=row_hash,
        occurred_at=_WHEN,
    )


class _FakeReader:
    """The one real seam this job depends on — an
    :class:`~ai_os_kernel.observability.audit_verification_job.
    AuditChainReader`, satisfied structurally, no mocking framework."""

    def __init__(self, records: list[AuditLogRecord]) -> None:
        self._records = records

    async def list_all(self) -> list[AuditLogRecord]:
        return list(self._records)


def _healthy_chain() -> list[AuditLogRecord]:
    r1 = _record(seq=1, audit_id="aud_1", prev_hash=None)
    r2 = _record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash)
    return [r1, r2]


def _tampered_chain() -> list[AuditLogRecord]:
    r1 = _record(seq=1, audit_id="aud_1", prev_hash=None)
    r2 = _record(seq=2, audit_id="aud_2", prev_hash=r1.row_hash)
    # A real tamper: rebuild r2 with different detail but the same (now
    # stale) row_hash — exactly what a direct-SQL edit that never
    # touches row_hash produces.
    r2_tampered = r2.model_copy(update={"detail": {"n": "tampered"}})
    return [r1, r2_tampered]


def test_a_single_pass_over_a_healthy_chain_passes_and_logs_no_alert() -> None:
    with structlog.testing.capture_logs() as logs:
        result = asyncio.run(run_audit_chain_verification_once(_FakeReader(_healthy_chain())))

    assert result.valid is True
    events = [entry["event"] for entry in logs]
    assert "audit_chain_verification.passed" in events
    assert "audit_chain_verification.broken" not in events


def test_a_single_pass_over_a_tampered_chain_is_caught_and_alerted() -> None:
    with structlog.testing.capture_logs() as logs:
        result = asyncio.run(run_audit_chain_verification_once(_FakeReader(_tampered_chain())))

    assert result.valid is False
    assert result.broken_at_seq == 2

    alerts = [entry for entry in logs if entry["event"] == "audit_chain_verification.broken"]
    assert len(alerts) == 1
    assert alerts[0]["log_level"] == "error"
    assert alerts[0]["broken_at_seq"] == 2
    assert alerts[0]["reason"] == result.reason


class _ScheduledReader:
    """Wraps a fixed set of records and sets ``stop_event`` once it has
    been read ``stop_after`` times — proves the loop genuinely iterates
    on a real interval, with the stop condition driven by the reader
    itself rather than a polling loop in the test."""

    def __init__(
        self, records: list[AuditLogRecord], *, stop_event: asyncio.Event, stop_after: int
    ) -> None:
        self._records = records
        self._stop_event = stop_event
        self._stop_after = stop_after
        self.call_count = 0

    async def list_all(self) -> list[AuditLogRecord]:
        self.call_count += 1
        if self.call_count >= self._stop_after:
            self._stop_event.set()
        return list(self._records)


def test_a_healthy_chain_passes_verification_repeatedly_on_a_real_schedule() -> None:
    """Proves the *scheduling*, not just one pass: a real
    ``asyncio`` interval loop runs the check more than once before the
    caller stops it."""
    stop_event = asyncio.Event()
    reader = _ScheduledReader(_healthy_chain(), stop_event=stop_event, stop_after=2)

    with structlog.testing.capture_logs() as logs:
        asyncio.run(
            run_periodic_audit_chain_verification(
                reader, interval_seconds=0.01, stop_event=stop_event
            )
        )

    assert reader.call_count >= 2
    passed = [e for e in logs if e["event"] == "audit_chain_verification.passed"]
    assert len(passed) >= 2
    assert not any(e["event"] == "audit_chain_verification.broken" for e in logs)


def test_a_tampered_chain_is_caught_on_schedule_and_the_loop_stops_cleanly() -> None:
    """The other half of the real property this Task's Output names:
    "Pass, or the first broken link" — on a real schedule, not just a
    single manual call."""
    stop_event = asyncio.Event()
    reader = _ScheduledReader(_tampered_chain(), stop_event=stop_event, stop_after=1)

    with structlog.testing.capture_logs() as logs:
        asyncio.run(
            run_periodic_audit_chain_verification(
                reader, interval_seconds=0.01, stop_event=stop_event
            )
        )

    alerts = [e for e in logs if e["event"] == "audit_chain_verification.broken"]
    assert len(alerts) == 1
    assert alerts[0]["broken_at_seq"] == 2
