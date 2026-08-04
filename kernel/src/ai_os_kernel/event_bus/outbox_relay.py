"""The Outbox Relay (event_bus.md §4's "Outbox Relay" box,
``P02-S07-M17-T03``, FR-014: "Drain the outbox at least once") — closes
the durable, cross-process half of the Event Bus by reading
``platform.event_outbox`` rows (``P02-S07-M17-T01``'s schema) and
republishing each through the real, unchanged
:class:`~ai_os_kernel.event_bus.bus.InProcessEventBus`
(``P02-S07-M17-T02``). No parallel dispatch mechanism: this module adds
no publish/subscribe logic of its own, only a bounded polling loop over
the same, existing :meth:`~ai_os_kernel.event_bus.bus.EventBus.publish`.

Row-claiming reuses the identical, already-proven
``SELECT ... FOR UPDATE SKIP LOCKED`` pattern
:meth:`ai_os_kernel.workflow_engine.lease.SqlWorkflowLeaseRepository.
reap_expired` established for exactly this "many possible concurrent
relay workers scanning the same table" shape — a row another relay
worker is mid-dispatching is skipped this pass, not blocked on.

**A real, disclosed schema limitation.** ``platform.event_outbox``
(``data_model.md`` §10) carries ``event_type``/``schema_version``/
``payload``/``trace_id``/``created_at`` — deliberately no ``source`` or
``workflow_id`` column (no writer exists yet either; this ticket does
not add one). Rebuilt :class:`~ai_os_kernel.event_bus.models.Event`\\ s
therefore use ``source=OUTBOX_RELAY_SOURCE`` (a real, honest fact — the
relay genuinely is the immediate republishing source, distinct from
whatever process originally wrote the row) and ``workflow_id=None``.
``event_id`` reuses the row's own ``outbox_id`` (already a stable,
unique id) rather than minting a new one for the same underlying
event — satisfying this ticket's own "published events with
correlation ids" output together with the passed-through ``trace_id``.

**A real, disclosed retry limitation.** ``attempts`` is incremented on
every dispatch attempt, success or failure, and ``dispatched_at`` is
only set on success, so a failed row is a genuine candidate again next
pass. There is no max-attempts/dead-letter cutoff: the table has no
column for one, and inventing that behavior beyond what §10 documents
would be exactly the "placeholder architecture" this codebase's own
coding standards disallow.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.event_bus.bus import EventBus
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.persistence.platform_schema import event_outbox

_logger = get_logger(__name__)

OUTBOX_RELAY_SOURCE = "platform.event_outbox"

# Matches ai_os_kernel.workflow_engine.lease_reaper.LEASE_REAP_BATCH_LIMIT /
# .scheduler.SCHEDULER_BATCH_LIMIT, this codebase's own established
# "reasonable batch size" convention, rather than inventing a new one.
OUTBOX_RELAY_BATCH_LIMIT = 100
# No document names a specific relay cadence (event_bus.md §4 documents
# the mechanism, not a number) -- reusing
# ai_os_kernel.workflow_engine.scheduler.SCHEDULER_INTERVAL_SECONDS'
# own already-decided cadence for the identical "discover due rows,
# act, repeat" loop shape.
OUTBOX_RELAY_INTERVAL_SECONDS = 5.0


class OutboxRelayResult(BaseModel):
    """What one :meth:`OutboxRelay.tick_once` pass dispatched."""

    model_config = ConfigDict(frozen=True)

    dispatched: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.dispatched)


class OutboxRelay:
    """Drains due ``platform.event_outbox`` rows into the injected
    :class:`~ai_os_kernel.event_bus.bus.EventBus` in bounded batches."""

    def __init__(self, engine: AsyncEngine, bus: EventBus) -> None:
        self._engine = engine
        self._bus = bus

    async def tick_once(self, *, limit: int) -> OutboxRelayResult:
        """Dispatch up to ``limit`` pending rows in one bounded pass."""
        async with self._engine.begin() as connection:
            candidates = await connection.execute(
                sa.select(event_outbox)
                .where(event_outbox.c.dispatched_at.is_(None))
                .order_by(event_outbox.c.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = candidates.mappings().all()
            if not rows:
                _logger.debug("outbox_relay.no_pending_rows", limit=limit)
                return OutboxRelayResult(dispatched=())

            dispatched: list[str] = []
            now = datetime.now(UTC)
            for row in rows:
                event = Event(
                    event_id=row["outbox_id"],
                    event_type=row["event_type"],
                    timestamp=row["created_at"],
                    source=OUTBOX_RELAY_SOURCE,
                    trace_id=row["trace_id"],
                    payload=row["payload"],
                    schema_version=row["schema_version"],
                )
                try:
                    await self._bus.publish(event)
                except Exception as exc:
                    _logger.error(
                        "outbox_relay.dispatch_failed",
                        outbox_id=row["outbox_id"],
                        error=str(exc),
                    )
                    await connection.execute(
                        sa.update(event_outbox)
                        .where(event_outbox.c.outbox_id == row["outbox_id"])
                        .values(attempts=event_outbox.c.attempts + 1)
                    )
                    continue

                await connection.execute(
                    sa.update(event_outbox)
                    .where(event_outbox.c.outbox_id == row["outbox_id"])
                    .values(dispatched_at=now, attempts=event_outbox.c.attempts + 1)
                )
                dispatched.append(row["outbox_id"])

        if dispatched:
            _logger.info("outbox_relay.dispatched", count=len(dispatched), outbox_ids=dispatched)
        return OutboxRelayResult(dispatched=tuple(dispatched))


async def run_outbox_relay_loop(
    *,
    relay: OutboxRelay,
    interval_seconds: float = OUTBOX_RELAY_INTERVAL_SECONDS,
    limit: int = OUTBOX_RELAY_BATCH_LIMIT,
) -> None:
    """Calls :meth:`OutboxRelay.tick_once` every ``interval_seconds``,
    until cancelled — the identical shape
    :func:`~ai_os_kernel.workflow_engine.scheduler.run_scheduler_loop`/
    :func:`~ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop`
    already establish, including sleeping *before* each pass (a freshly
    started Kernel has no outbox backlog yet) and a genuine per-tick
    failure being logged, not fatal to the loop."""
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                result = await relay.tick_once(limit=limit)
                if result.count:
                    _logger.info("outbox_relay.loop_dispatched", count=result.count)
            except Exception as exc:
                _logger.error("outbox_relay.loop_tick_failed", error=str(exc))
    except asyncio.CancelledError:
        _logger.info("outbox_relay.loop_stopped")
        raise
