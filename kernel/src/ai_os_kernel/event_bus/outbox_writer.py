"""The transactional-outbox *writer* (``P02-S07-M17-T04``) — the
producer half of ADR-0012 that
:mod:`ai_os_kernel.event_bus.outbox_relay` has been draining without.

Until this module existed, ``platform.event_outbox`` had no writer at
all: :mod:`ai_os_kernel.event_bus`'s own package docstring said so
outright ("No writer for ``platform.event_outbox`` exists yet"), and
``event_bus.md`` §4's Implementation Status recorded the relay as
draining "whatever a future writer would insert" — rows seeded directly
in tests. That made the relay, its migration, and the table real,
tested, and unreachable from production (risk register R-018's own
"proven but idle" shape).

**Why a connection, not an engine.** Every other persistence collaborator
in this codebase takes an ``AsyncEngine`` and opens its own transaction.
This one deliberately does not. ADR-0012's whole reason for existing is
that the event row is "written **in the same transaction as the state
change that produced them**", and ADR-0011 repeats the requirement — so
the writer has to join a transaction its caller already opened rather
than open a second one. Taking the caller's :class:`AsyncConnection` is
what makes the guarantee real instead of aspirational: if the caller's
transaction rolls back, the outbox row goes with it, and no notification
can ever describe a state change that did not commit.

**Which events belong here.** ``event_bus.md`` §5's decision table, not
this module's judgement: anything that "must survive a crash, or must
reach another process (workflow lifecycle, gate results, approvals,
Dashboard updates)" uses the outbox; loss-tolerable in-process fan-out
uses :meth:`~ai_os_kernel.event_bus.bus.InProcessEventBus.publish`
directly, as
:func:`~ai_os_kernel.evaluation_engine.cost_anomaly.
run_cost_anomaly_check_once` does for its own alert.

**The payload carries what the table cannot.** ``platform.event_outbox``
(``data_model.md`` §10) has no ``source`` or ``workflow_id`` column, so
the relay rebuilds every :class:`~ai_os_kernel.event_bus.models.Event`
with ``workflow_id=None`` — a real, already-disclosed limitation
documented on :mod:`ai_os_kernel.event_bus.outbox_relay` itself. A
caller that needs a subscriber to know *which* workflow an event is
about must therefore put the id in ``payload``, which
:class:`~ai_os_kernel.notification.service.NotificationService` passes
through to ``Notification.payload`` unchanged. Adding the columns
instead would be a schema change beyond what §10 documents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from ai_os_kernel.event_bus.ids import new_outbox_id
from ai_os_kernel.persistence.platform_schema import event_outbox

# The initial version of every event shape written through this module.
# Matches `Event.schema_version`'s own default and the identical `_
# WORKFLOW_EVENT_SCHEMA_VERSION = 1` convention `workflow_engine.
# repository` already uses for `workflow.workflow_events`. A caller
# evolving its own payload shape passes an explicit, higher value.
OUTBOX_SCHEMA_VERSION = 1


async def write_outbox_event(
    connection: AsyncConnection,
    *,
    event_type: str,
    payload: dict[str, Any],
    schema_version: int = OUTBOX_SCHEMA_VERSION,
    trace_id: str | None = None,
) -> str:
    """Insert one durable event into ``platform.event_outbox`` on
    ``connection``'s *already open* transaction, returning its
    ``outbox_id``.

    ``dispatched_at`` is deliberately left null and ``attempts`` left to
    the column's own ``server_default`` of ``0``: together they are
    exactly what makes the row a genuine candidate for
    :meth:`~ai_os_kernel.event_bus.outbox_relay.OutboxRelay.tick_once`'s
    ``dispatched_at IS NULL`` claim query. The relay reuses the returned
    id as the published ``Event.event_id``, which is why nothing here
    mints a separate one.
    """
    outbox_id = new_outbox_id()
    await connection.execute(
        sa.insert(event_outbox).values(
            outbox_id=outbox_id,
            event_type=event_type,
            schema_version=schema_version,
            payload=payload,
            trace_id=trace_id,
            created_at=datetime.now(UTC),
        )
    )
    return outbox_id
