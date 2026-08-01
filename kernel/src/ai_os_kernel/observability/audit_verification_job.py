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

**Wired into a real Kernel process as of ``P01-S04-M03-T06``.** Before
that step this job was built and unit-tested but never started
anywhere — ``ai_os_kernel.bootstrap._lifespan`` now starts it alongside
the Pack Health Collector and Lease Reaper loops, stopped on shutdown
through the same :class:`~ai_os_kernel.health.shutdown.GracefulShutdownCoordinator`
those two already use.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from ai_os_kernel.observability.audit import AuditLogRecord, ChainVerificationResult, verify_chain
from ai_os_kernel.observability.logging import get_logger

logger = get_logger(__name__)

# An integrity check, not an operational reap/health mechanism (contrast
# LEASE_REAP_INTERVAL_SECONDS=15.0, POLL_INTERVAL_SECONDS=30.0) — frequent
# enough to catch tampering promptly, infrequent enough to avoid scanning
# the whole, ever-growing audit_log table on every pass.
AUDIT_CHAIN_VERIFICATION_INTERVAL_SECONDS = 300.0


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

    **A genuine per-pass failure (a real database error) is logged and
    does not stop the loop** — the identical per-pass resilience
    :func:`~ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop`/
    :func:`~ai_os_kernel.capability_manager.health_poller.run_health_polling_loop`
    already establish for their own background loops. Discovered as a
    real, missing gap while wiring this job into a live process for the
    first time (``P01-S04-M03-T06``): without it, one transient
    connection failure would silently kill this entire background job
    for the rest of the process's life, and would surface through
    :class:`~ai_os_kernel.health.shutdown.GracefulShutdownCoordinator`
    as an uncaught exception out of a *shutdown* call — the opposite of
    graceful.
    """
    while not stop_event.is_set():
        try:
            await run_audit_chain_verification_once(reader)
        except Exception as exc:  # noqa: BLE001 -- a genuine per-pass failure must never kill the loop
            logger.error("audit_chain_verification.pass_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
