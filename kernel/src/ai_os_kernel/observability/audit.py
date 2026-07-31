"""The hash-chained ``governance.audit_log`` writer (FR-110, ADR-0017,
data_model.md §9.1) — ``P01-S05-M04-T05``, this table's first real
writer. Until now nothing computed ``row_hash``/``prev_hash`` or wrote a
row here at all (:mod:`ai_os_kernel.persistence.governance_schema`'s own
docstring: "no writer, for either table").

**Deliberately a separate module from the rest of `observability`,
mirroring that package's own docstring** ("Telemetry and audit are
deliberately different concerns — this package is telemetry only"):
audit is tamper-evident and never sampled (ADR-0017); telemetry is
neither.

**What "hash-chained" means here, concretely.** Each row's ``row_hash``
is a SHA-256 digest over that row's own real column values *plus* the
immediately preceding row's real ``row_hash`` (``prev_hash``). Mutating
any persisted value on a row — after the fact, directly in the database
— makes that row's own stored ``row_hash`` disagree with a fresh
recomputation from its (now different) content, which
:func:`verify_chain` detects and reports. Rewriting `row_hash` too, to
hide the edit, still breaks the *next* row's `prev_hash` link; forging
the whole chain requires rewriting every row after the tampered one —
the standard security property a hash chain provides, not a gap this
step needs to close further.

**Concurrency: a real Postgres advisory lock, not "hope for the
best".** Computing the next `row_hash` needs the *current* latest row's
real hash, read inside the same transaction as the insert. Two
concurrent callers naively doing "read latest, then insert" could both
read the same latest hash and each insert a row claiming to be its
successor — silently forking the chain. `pg_advisory_xact_lock` held for
the read-latest-then-insert serializes every append to this one table,
automatically released at transaction end; every other table in this
codebase either doesn't have this problem (workflow_steps' own
``attempt`` uses `MAX(attempt)+1` inside one transaction with no chained
identity to protect) or hasn't needed one yet.

**Verification lives here, not in a scheduled job.** data_model.md §9.1
also names "a scheduled job [that] verifies the chain and alerts on a
break" — genuinely separate, later work (``P01-S05-M04-T06``,
depends_on this Task): *running :func:`verify_chain` on an interval and
alerting* is that job's whole content. The verification logic itself has
to exist now, for the same reason a writer with no way to prove its own
claim would not be a real hash chain at all.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.observability.errors import AuditLogError
from ai_os_kernel.observability.ids import new_audit_id
from ai_os_kernel.observability.trace import get_trace_id
from ai_os_kernel.persistence.governance_schema import audit_log


# The exact four values data_model.md §9.1 documents, and the CHECK
# constraint governance_schema.py already enforces — named here so a
# caller gets a clear ValueError at construction time instead of a raw
# CHECK-constraint failure surfacing from the database.
class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    SUCCESS = "success"
    FAILURE = "failure"


# A fixed, named key — never a bare literal at the call site — for the
# one advisory lock this module ever takes. Scoped to this table by its
# own qualified name; `hashtext()` (Postgres builtin) turns it into the
# integer `pg_advisory_xact_lock` requires.
_ADVISORY_LOCK_KEY = "governance.audit_log"


class AuditLogRecord(BaseModel):
    """One real, persisted ``governance.audit_log`` row — what
    :func:`verify_chain` checks, and what
    :meth:`SqlAuditLogWriter.list_all` returns."""

    model_config = ConfigDict(frozen=True)

    audit_id: str
    seq: int
    event_type: str
    principal_id: str
    principal_type: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    detail: dict[str, Any]
    trace_id: str | None
    prev_hash: str | None
    row_hash: str
    occurred_at: datetime


class ChainVerificationResult(BaseModel):
    """The real outcome of :func:`verify_chain` — a result to inspect,
    never an exception to catch, the same "structured report, not a
    raised failure" shape :class:`~ai_os_kernel.health.service.
    ComponentStatus` already established for a check that can fail."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    broken_at_seq: int | None = None
    reason: str | None = None


def compute_row_hash(
    *,
    audit_id: str,
    event_type: str,
    principal_id: str,
    principal_type: str,
    resource_type: str | None,
    resource_id: str | None,
    outcome: str,
    detail: dict[str, Any],
    trace_id: str | None,
    occurred_at: datetime,
    prev_hash: str | None,
) -> str:
    """The one hashing routine both the writer and the verifier use —
    computed identically in both places so they can never silently
    drift apart.

    ``occurred_at`` is normalised to UTC before hashing. The column is
    ``TIMESTAMP(timezone=True)``: Postgres stores an absolute instant
    and may hand it back through a different session time zone than the
    one it was written with, which would otherwise change
    ``.isoformat()``'s own string for a row nobody tampered with at
    all — normalising first makes the hash depend on the real instant,
    never on which time zone happened to read it back.
    """
    payload = {
        "audit_id": audit_id,
        "event_type": event_type,
        "principal_id": principal_id,
        "principal_type": principal_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
        "detail": detail,
        "trace_id": trace_id,
        "occurred_at": occurred_at.astimezone(UTC).isoformat(),
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_chain(records: Sequence[AuditLogRecord]) -> ChainVerificationResult:
    """Walks ``records`` in ``seq`` order and confirms every row's real,
    recomputed hash matches what it claims, and that every row's
    ``prev_hash`` is genuinely the previous row's real ``row_hash`` —
    not merely whatever that row's own ``prev_hash`` column happens to
    say. An empty chain is trivially valid (nothing to break)."""
    prev_hash: str | None = None
    for record in sorted(records, key=lambda r: r.seq):
        if record.prev_hash != prev_hash:
            return ChainVerificationResult(
                valid=False,
                broken_at_seq=record.seq,
                reason=(
                    f"row {record.audit_id!r} (seq {record.seq}): prev_hash does not "
                    "match the prior row's real row_hash"
                ),
            )
        expected = compute_row_hash(
            audit_id=record.audit_id,
            event_type=record.event_type,
            principal_id=record.principal_id,
            principal_type=record.principal_type,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            outcome=record.outcome,
            detail=record.detail,
            trace_id=record.trace_id,
            occurred_at=record.occurred_at,
            prev_hash=record.prev_hash,
        )
        if expected != record.row_hash:
            return ChainVerificationResult(
                valid=False,
                broken_at_seq=record.seq,
                reason=(
                    f"row {record.audit_id!r} (seq {record.seq}): row_hash does not match "
                    "a recomputation of its own content — this row was modified after "
                    "it was written"
                ),
            )
        prev_hash = record.row_hash
    return ChainVerificationResult(valid=True)


class AuditLogWriter(Protocol):
    """Persistence boundary for recording one significant, audited
    action — the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def record(
        self,
        *,
        event_type: str,
        principal_id: str,
        principal_type: str,
        outcome: AuditOutcome,
        detail: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
    ) -> None: ...


class SqlAuditLogWriter:
    """The only implementation of :class:`AuditLogWriter` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(
        self,
        *,
        event_type: str,
        principal_id: str,
        principal_type: str,
        outcome: AuditOutcome,
        detail: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        # The real, already-established correlation mechanism
        # (TraceIdMiddleware binds this per request) — never invented
        # here, and never required: a caller with no active request
        # (a background job) still gets a real, honest `None`.
        if trace_id is None:
            trace_id = get_trace_id()
        occurred_at = datetime.now(UTC)
        audit_id = new_audit_id()

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": _ADVISORY_LOCK_KEY},
                )
                prev_hash = (
                    await connection.execute(
                        sa.select(audit_log.c.row_hash).order_by(audit_log.c.seq.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                row_hash = compute_row_hash(
                    audit_id=audit_id,
                    event_type=event_type,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    outcome=outcome,
                    detail=detail,
                    trace_id=trace_id,
                    occurred_at=occurred_at,
                    prev_hash=prev_hash,
                )

                await connection.execute(
                    sa.insert(audit_log).values(
                        audit_id=audit_id,
                        event_type=event_type,
                        principal_id=principal_id,
                        principal_type=principal_type,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        outcome=outcome,
                        detail=detail,
                        trace_id=trace_id,
                        prev_hash=prev_hash,
                        row_hash=row_hash,
                        occurred_at=occurred_at,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise AuditLogError(
                f"failed to record audit event {event_type!r} for principal {principal_id!r}: {exc}"
            ) from exc

    async def list_all(self) -> list[AuditLogRecord]:
        """Every real, persisted row, ordered by ``seq`` — what a real
        verification pass (this Task's own tests, and the later
        scheduled job) reads."""
        async with self._engine.connect() as connection:
            rows = (
                (await connection.execute(sa.select(audit_log).order_by(audit_log.c.seq)))
                .mappings()
                .all()
            )
        return [AuditLogRecord.model_validate(dict(row)) for row in rows]
