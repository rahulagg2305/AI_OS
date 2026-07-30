"""The Pack Health Collector — the smallest real slice of
capability_manager.md §9's own named "health check protocols" gap:
"nobody has decided *who calls a pack's health check and how often* —
poll interval, timeout, and the number of consecutive failures that
moves a pack to `failed`."

**The three-value policy, decided here, for the first time:**

- ``POLL_INTERVAL_SECONDS`` (30.0) — how often a real deployment should
  call :func:`poll_pack_health` for each activated pack. **Not enforced
  by this module** — there is no background scheduler yet, deliberately
  out of this step's own "smallest real slice" scope, the identical,
  already-accepted "no full worker scheduler" gap this codebase already
  carries for the Workflow Engine (see ``bootstrap.py``'s own
  docstring). A future scheduler/cron reads this constant rather than
  inventing its own number; today, the one real caller
  (``ai_os_kernel.bootstrap``) runs exactly one poll per pack per
  Kernel startup. Chosen as heavier than a liveness ping (which checks
  nothing real) but lighter than a human-scale operational window.
- ``POLL_TIMEOUT_SECONDS`` (5.0) — bounds *one* agent-resolution
  attempt within a poll cycle, so a genuinely hung resolution (a
  stalled import, a stuck DB query) cannot hang the whole poll — or
  whatever real caller is waiting on it (Kernel startup, today).
  Deliberately more generous than
  :data:`ai_os_kernel.bootstrap._DATABASE_CHECK_TIMEOUT_SECONDS` (2.0s):
  resolving an agent can import a whole pack module on first use,
  genuinely slower than one bare SQL round trip.
- ``CONSECUTIVE_FAILURE_THRESHOLD`` (3) — the number of consecutive
  unhealthy polls before a pack is genuinely moved to
  :attr:`~ai_os_kernel.workflow_engine.pack_state.PackState.FAILED`.
  Matches Kubernetes' own default ``failureThreshold`` for exactly this
  kind of consecutive-failure escalation — a real, externally-precedented
  number, not invented from nothing.

**Genuinely tests reachability, not just "is the row activated"** — the
one real check this step builds resolves *every one* of the pack's own
``catalog.agents`` rows through a real
:class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry` (the same
real registry a caller would use to actually run that agent, so a
missing LLM secret genuinely reported as "unhealthy" here is an honest
signal, not a poller-specific false negative — see
:func:`~ai_os_kernel.bootstrap._build_se_delivery_pipeline_registry`'s
own docstring for why that registry's ``llm_gateway`` can itself be
``None``). A pack with zero declared agents (the schema-valid,
capability-less ``_template`` example pack) is vacuously healthy —
there is nothing to fail.

**Always writes a real ``catalog.packs.health`` snapshot** — healthy or
not, via
:meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.record_health`
— the Pack Health Collector's own real job, distinct from the
``mark_failed()`` state transition, which only fires once
``consecutive_failures`` (tracked inside that same snapshot, read back
from the previous poll) crosses ``CONSECUTIVE_FAILURE_THRESHOLD``.

**``POLL_INTERVAL_SECONDS`` is now genuinely enforced (2026-07-30) —
:func:`run_health_polling_loop` is the real background scheduler the
module docstring above originally deferred.** This is the first real,
continuously-running background task anywhere in this codebase — the
Workflow Engine's own analogous job,
:class:`~ai_os_kernel.workflow_engine.lease_reaper.WorkflowLeaseReaper`,
deliberately stops at "reclaim once, in one bounded pass" and
documents scheduling as a future worker-process framework's job; this
step is that framework's first real instance, scoped narrowly to this
one, already-decided policy value rather than a general-purpose one.
Sleeps for ``interval_seconds`` *before* each poll pass (not after) so
the loop never duplicates the one-shot poll a caller already performed
at startup (``ai_os_kernel.bootstrap._poll_discovered_pack_health`,
unchanged by this step) — the loop's own first real poll lands one
full interval later, not immediately. Exits cleanly on
``asyncio.CancelledError`` (the real signal a caller cancelling the
wrapping ``asyncio.Task`` sends on shutdown) — logged, then re-raised,
so the awaiting ``Task`` itself genuinely completes as cancelled, not
silently swallowed into "finished normally."
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import PackLifecycleRepository
from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.persistence.catalog_schema import agents as agents_table
from ai_os_kernel.workflow_engine.registry import AgentRegistry
from ai_os_sdk.contracts.capability_pack import HealthReport

_logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 30.0
POLL_TIMEOUT_SECONDS = 5.0
CONSECUTIVE_FAILURE_THRESHOLD = 3


async def poll_pack_health(
    *,
    engine: AsyncEngine,
    pack_lifecycle_repository: PackLifecycleRepository,
    agent_registry: AgentRegistry,
    pack_id: str,
    actor: str,
) -> HealthReport:
    """One real poll cycle for one activated pack — see this module's
    own docstring for the full design (the three-value policy, why the
    check is genuine, why a snapshot is always written).

    A ``mark_failed()`` rejection (the pack is no longer ``ACTIVATED``
    for some other real reason, observed concurrently) is not this
    function's problem to raise over — the health snapshot itself is
    written either way, and the caller already has the returned
    :class:`HealthReport` regardless of whether the state transition
    itself was able to apply.
    """
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(agents_table.c.agent_id).where(agents_table.c.pack_id == pack_id)
        )
        agent_ids = [row.agent_id for row in result]

    failed_agents: dict[str, str] = {}
    for agent_id in agent_ids:
        try:
            await asyncio.wait_for(
                agent_registry.resolve_agent(agent_id), timeout=POLL_TIMEOUT_SECONDS
            )
        except Exception as exc:
            failed_agents[agent_id] = str(exc)

    report = (
        HealthReport(
            status="unhealthy",
            details={"agents_checked": len(agent_ids), "failed_agents": failed_agents},
        )
        if failed_agents
        else HealthReport(status="healthy", details={"agents_checked": len(agent_ids)})
    )

    previous = await pack_lifecycle_repository.get_pack(pack_id)
    previous_consecutive_failures: int = 0
    if previous is not None and previous.health is not None:
        previous_consecutive_failures = previous.health.get("consecutive_failures", 0)
    consecutive_failures = 0 if report.status == "healthy" else previous_consecutive_failures + 1

    health_snapshot: dict[str, Any] = {
        "status": report.status,
        "details": report.details,
        "consecutive_failures": consecutive_failures,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    await pack_lifecycle_repository.record_health(pack_id=pack_id, health=health_snapshot)

    if consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
        with contextlib.suppress(CapabilityManagerError):
            await pack_lifecycle_repository.mark_failed(
                pack_id=pack_id,
                actor=actor,
                reason=(
                    f"{consecutive_failures} consecutive unhealthy polls "
                    f"(threshold={CONSECUTIVE_FAILURE_THRESHOLD})"
                ),
            )

    return report


async def run_health_polling_loop(
    *,
    engine: AsyncEngine,
    pack_lifecycle_repository: PackLifecycleRepository,
    agent_registry: AgentRegistry,
    pack_ids: Collection[str],
    actor: str,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Calls :func:`poll_pack_health` for every ``pack_id`` in
    ``pack_ids``, every ``interval_seconds``, until cancelled — see this
    module's own docstring for the full design (why it sleeps first, why
    this is genuinely new infrastructure, how it shuts down cleanly).

    ``pack_ids`` is a fixed snapshot the caller already discovered
    (``ai_os_kernel.bootstrap._register_and_activate_discovered_packs``'s
    own return value) — this function decides *when* to poll, never
    *what*; re-discovering packs mid-process is a distinct, later
    capability, not attempted here.

    A genuine per-pack polling failure (a real database error, not
    merely an unhealthy pack — that is ``poll_pack_health``'s own
    correctly-reported outcome) is logged and does not stop the loop or
    abort polling the other packs in the same pass — the identical
    per-item resilience
    :func:`~ai_os_kernel.bootstrap._poll_discovered_pack_health` already
    established for the one-shot startup poll.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            for pack_id in pack_ids:
                try:
                    report = await poll_pack_health(
                        engine=engine,
                        pack_lifecycle_repository=pack_lifecycle_repository,
                        agent_registry=agent_registry,
                        pack_id=pack_id,
                        actor=actor,
                    )
                    _logger.info(
                        "health_poller.polling_loop_polled", pack_id=pack_id, status=report.status
                    )
                except Exception as exc:
                    _logger.error(
                        "health_poller.polling_loop_poll_failed", pack_id=pack_id, error=str(exc)
                    )
    except asyncio.CancelledError:
        _logger.info("health_poller.polling_loop_stopped")
        raise
