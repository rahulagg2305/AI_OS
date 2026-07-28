"""Canonical Core table definitions for governance/audit persistence.

Mirrors docs/08_database/data_model.md §9 exactly. Kept in its own
module with its own ``MetaData`` (schema ``governance``), separate
from :mod:`ai_os_kernel.persistence.schema` (schema ``workflow``) — a
genuinely distinct bounded context, not workflow state. Both modules'
``MetaData`` objects are combined into one ``target_metadata`` sequence
in ``kernel/alembic/env.py`` (Alembic supports a sequence of
``MetaData`` objects there).

Two tables are defined here: ``audit_log`` and ``config_changes`` —
every table data_model.md §9 documents for the ``governance`` schema.

Schema and migration only — no writer, for either table. ADR-0017 draws
a hard line between this path (tamper-evident, hash-chained, never
sampled) and the OTLP telemetry path (:mod:`ai_os_kernel.observability`);
nothing yet computes ``row_hash``/``prev_hash`` or a digest, or writes a
row here, and no component that would need to (Security Manager,
Workflow Engine, Configuration Manager, ...) is built out far enough to.

``audit_log`` (§9.1):

- ``event_type`` deliberately has no ``CHECK`` constraint: data_model.md
  §9.1 lists example values (``auth.success``, ``authz.denied``, …)
  ending in an ellipsis — an explicitly open-ended, illustrative set,
  exactly the same reasoning already applied to
  ``ai_os_kernel.persistence.schema.workflow_events.event_type``.
  ``outcome`` *does* get one: §9.1 gives it an explicit four-value list
  (``allowed``/``denied``/``success``/``failure``), the same "canonical
  list is documented, so enforce it" reasoning already applied to
  ``workflow_instances.status`` and ``approvals.status``.
- ``seq`` is documented as ``bigserial NOT NULL UNIQUE`` — an
  auto-incrementing bigint used for global ordering. Implemented as a
  SQL-standard ``GENERATED ... AS IDENTITY`` column
  (:class:`sqlalchemy.Identity`) rather than the legacy Postgres
  ``BIGSERIAL`` pseudo-type: both produce an auto-incrementing bigint
  backed by an implicit sequence with identical insert behaviour, and
  ``IDENTITY`` is what current Postgres and SQLAlchemy documentation
  recommend for new schemas.
- Two documented details are intentionally deferred, not silently
  dropped, mirroring the same deferrals already made for
  ``workflow_events``: ``UPDATE``/``DELETE`` revocation for "the
  application role" (no such role exists yet), and the scheduled
  hash-chain verification job (data_model.md §9.1: "A scheduled job
  verifies the chain and alerts on a break" — no worker process
  framework exists yet to run it in; see
  docs/19_roadmap/implementation_status.md §4).
- No foreign key: unlike ``workflow_steps``/``workflow_leases``/
  ``approvals``, §9.1 does not scope this table to workflow instances
  at all — ``resource_type``/``resource_id`` are a loose, polymorphic
  pointer (auth events, secret access, pack lifecycle, sandbox
  executions, ... not only workflows), so there is no single table to
  reference.

``config_changes`` (§9.2): every column is a plain scalar (no jsonb, no
enum-like column), so there is nothing here to add a ``CHECK``
constraint for and nothing to type as anything but ``sa.Text``/
``sa.TIMESTAMP``. §9.2 marks no column nullable, but two are reasoned
as such rather than invented outright: ``old_value_digest`` is ``NULL``
for a config key's first-ever value (there is no prior value to
digest); ``new_value_digest`` is ``NULL`` when a change removes a key
entirely (there is no new value to digest) — an "update" row has both.
``config_key``, ``changed_by``, ``reason``, and ``changed_at`` are
``NOT NULL``: every governance-relevant change has a key, an actor, a
recorded reason (the same "every record of this kind must carry a
reason" rule already enforced for ``workflow_instances``' own
``state.transitioned`` event), and a time. No foreign key, for the same
reason ``audit_log`` has none: nothing scopes a configuration key to
one specific table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(schema="governance")

_AUDIT_OUTCOMES = (
    "allowed",
    "denied",
    "success",
    "failure",
)

audit_log = sa.Table(
    "audit_log",
    metadata,
    sa.Column("audit_id", sa.Text, primary_key=True),
    sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False, unique=True),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("principal_id", sa.Text, nullable=False),
    sa.Column("principal_type", sa.Text, nullable=False),
    sa.Column("resource_type", sa.Text, nullable=True),
    sa.Column("resource_id", sa.Text, nullable=True),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("detail", JSONB, nullable=False),
    sa.Column("trace_id", sa.Text, nullable=True),
    sa.Column("prev_hash", sa.Text, nullable=True),
    sa.Column("row_hash", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.CheckConstraint(
        "outcome IN (" + ", ".join(f"'{o}'" for o in _AUDIT_OUTCOMES) + ")",
        name="ck_audit_log_outcome",
    ),
)

sa.Index("ix_audit_log_event_type", audit_log.c.event_type)
sa.Index("ix_audit_log_occurred_at_desc", audit_log.c.occurred_at.desc())
sa.Index("ix_audit_log_trace_id", audit_log.c.trace_id)

config_changes = sa.Table(
    "config_changes",
    metadata,
    sa.Column("change_id", sa.Text, primary_key=True),
    sa.Column("config_key", sa.Text, nullable=False),
    sa.Column("old_value_digest", sa.Text, nullable=True),
    sa.Column("new_value_digest", sa.Text, nullable=True),
    sa.Column("changed_by", sa.Text, nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("changed_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_config_changes_config_key", config_changes.c.config_key)
sa.Index("ix_config_changes_changed_at_desc", config_changes.c.changed_at.desc())
