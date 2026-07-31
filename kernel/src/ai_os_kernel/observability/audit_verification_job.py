"""Scheduled ``governance.audit_log`` hash-chain verification job
(``P01-S05-M04-T06``, data_model.md §9.1: "a scheduled job [that]
verifies the chain and alerts on a break").

:mod:`ai_os_kernel.observability.audit`'s own docstring named this as
deliberately separate, later work: the hard part —
:func:`~ai_os_kernel.observability.audit.verify_chain` — already exists
and is proven by that Task's own tests. This module is only the
interval loop and the alert, kept genuinely small on purpose.

**"Alert" here means a real ERROR-level structured log entry** — this
codebase's own alerting idiom (:mod:`ai_os_kernel.observability.logging`:
"the only supported way to obtain a logger"), not a new notification
channel invented for this one job.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from ai_os_kernel.observability.audit import AuditLogRecord, ChainVerificationResult, verify_chain
from ai_os_kernel.observability.logging import get_logger

logger = get_logger(__name__)


class AuditChainReader(Protocol):
    """The read side this job needs — :class:`~ai_os_kernel.observability.
    audit.SqlAuditLogWriter` already satisfies this structurally via its
    own ``list_all``."""

    async def list_all(self) -> list[AuditLogRecord]: ...


async def run_audit_chain_verification_once(reader: AuditChainReader) -> ChainVerificationResult:
    """One real verification pass: read every persisted row, verify the
    chain, and alert the instant it's broken. Returns the result so a
    caller (or a test) can inspect it directly, in addition to the log
    entry this always emits."""
    records = await reader.list_all()
    result = verify_chain(records)
    if result.valid:
        logger.info("audit_chain_verification.passed", row_count=len(records))
    else:
        logger.error(
            "audit_chain_verification.broken",
            broken_at_seq=result.broken_at_seq,
            reason=result.reason,
        )
    return result


async def run_periodic_audit_chain_verification(
    reader: AuditChainReader,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event,
) -> None:
    """Runs :func:`run_audit_chain_verification_once` every
    ``interval_seconds`` until ``stop_event`` is set.

    The caller (process bootstrap) owns ``stop_event``, so a clean
    shutdown never leaves this loop dangling — the same "the caller
    controls the lifetime" shape already used wherever this codebase
    runs a background loop. Neither the interval nor the reader is
    hardcoded here; both are the caller's real configuration.
    """
    while not stop_event.is_set():
        await run_audit_chain_verification_once(reader)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
