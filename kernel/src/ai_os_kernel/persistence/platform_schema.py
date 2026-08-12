"""Canonical Core table definitions for platform-infrastructure
persistence.

Mirrors docs/08_database/data_model.md §10, in the same style as
:mod:`ai_os_kernel.persistence.governance_schema`: kept in its own
module with its own ``MetaData`` (schema ``platform``), a genuinely
distinct bounded context from both ``workflow`` and ``governance``.
Combined into ``target_metadata`` in ``kernel/alembic/env.py`` alongside
the other two.

Two of the three tables §10 documents are defined here: ``event_outbox``
and ``idempotency_keys``. ``platform.schema_metadata`` is **deliberately
not defined here** — unlike every other table added so far, §10 gives
it no column list at all, only a purpose description ("Alembic revision
plus ``index_generation`` counters for retrieval"), and the plural
"counters" is ambiguous about shape (one global counter, or one per
indexed resource?). Inventing column names for it would cross the line
this whole persistence layer has held since the very first migration:
every table here mirrors a documented column list exactly. Add it once
data_model.md names its columns.

``event_outbox`` is ADR-0012's transactional outbox ("written in the
same transaction as the state change that produced the event"). **This
paragraph was stale until 2026-08-12** and is corrected rather than
quietly rewritten: it said "nothing in this codebase writes to an outbox
yet ... and the Event Bus itself (in-process pub/sub plus the outbox
relay) does not exist yet." The Event Bus shipped in ``P02-S07-M17-T02``
and its relay in ``P02-S07-M17-T03``; the first real writer arrived in
``P02-S07-M17-T04`` —
:func:`~ai_os_kernel.event_bus.outbox_writer.write_outbox_event`, which
takes the caller's ``AsyncConnection`` precisely so this table's
defining same-transaction property is structural. Its first producer is
:meth:`~ai_os_kernel.workflow_engine.repository.
SqlWorkflowInstanceRepository.advance_workflow`'s terminal
``workflow.completed`` branch. ``workflow_events`` remains a separate,
unchanged concern — this engine's own event-*sourcing* log, read by
``GET /workflows/{id}/events`` and subscribed to by nothing.

``idempotency_keys`` now has a real reader/writer (``P06-S01-M36-T03``,
2026-08-06): :class:`~ai_os_kernel.routes.idempotency.
SqlIdempotencyKeyStore`, backing
:class:`~ai_os_kernel.routes.idempotency.IdempotencyKeyMiddleware` —
a real ASGI middleware, generic across every mutating HTTP route, not
a per-route mechanism. See that module's own docstring for the full
design (replay/conflict semantics, the real, disclosed race window
under genuine concurrency).

``event_outbox``:

- Column-for-column per §10: ``outbox_id`` PK, ``event_type``,
  ``schema_version``, ``payload`` (jsonb), ``trace_id``, ``created_at``,
  ``dispatched_at`` (explicitly nullable — unset until the relay
  dispatches it), ``attempts``.
- Types/nullability for ``event_type``/``schema_version``/``payload``/
  ``trace_id``/``created_at`` mirror
  ``ai_os_kernel.persistence.schema.workflow_events`` exactly — the
  same four fields, same meaning, same table shape.
- ``attempts`` is ``NOT NULL`` with a ``0`` default: a freshly
  outboxed event has not been attempted yet, mirroring the same
  "counter starts at zero" reasoning as
  ``workflow_instances.total_tokens``/``total_cost_usd``.
- No ``CHECK`` constraint on ``event_type``: the same open-ended-set
  reasoning already applied to ``workflow_events.event_type`` and
  ``audit_log.event_type`` — this table can and will outbox many of the
  same event types workflow_events already carries.

``idempotency_keys``:

- Column-for-column per §10: ``key`` PK, ``principal_id``,
  ``request_digest``, ``response`` (jsonb), ``status_code``,
  ``created_at``, ``expires_at``. §10 marks none of these nullable, so
  none are — this table's own documented shape is "write the row once
  the response is known," not a two-phase write.
- ``expires_at``'s "(24 h)" note is the TTL duration a future writer
  computes (``created_at`` + 24 hours), not a schema-level default —
  no ``GENERATED`` column is introduced for it, matching how
  ``workflow_leases.expires_at`` is likewise a plain column set by
  application code, never database-computed.

No foreign keys on either table: both are cross-cutting infrastructure
tables (any event, any request), not scoped to one specific row in
another table — the same reasoning already applied to ``audit_log`` and
``config_changes``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(schema="platform")

event_outbox = sa.Table(
    "event_outbox",
    metadata,
    sa.Column("outbox_id", sa.Text, primary_key=True),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("schema_version", sa.Integer, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("trace_id", sa.Text, nullable=True),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("dispatched_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
)

sa.Index("ix_event_outbox_dispatched_at", event_outbox.c.dispatched_at)
sa.Index("ix_event_outbox_created_at", event_outbox.c.created_at)

idempotency_keys = sa.Table(
    "idempotency_keys",
    metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("principal_id", sa.Text, nullable=False),
    sa.Column("request_digest", sa.Text, nullable=False),
    sa.Column("response", JSONB, nullable=False),
    sa.Column("status_code", sa.Integer, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_idempotency_keys_expires_at", idempotency_keys.c.expires_at)
