"""Canonical Core table definition for
``notification.notification_deliveries`` (`P06-S05-M22-T02`).

Its own schema, its own ``MetaData``, mirroring every other bounded
context in this codebase (``workflow``, ``governance``, ``context``,
...) — the identical "one schema per genuinely distinct bounded
context" precedent :mod:`ai_os_kernel.context_manager.schema`'s own
docstring already states. Combined into Alembic's own
``target_metadata`` sequence in ``kernel/alembic/env.py``, the
identical mechanism every other schema module already uses.

``workflow_id`` is a plain, unconstrained column, not a cross-schema
foreign key to ``workflow_instances`` — the identical choice
``context.context_assemblies`` already makes for the same real reason:
it is genuinely nullable here (a notification triggered by a
non-workflow-scoped event has none), and the cross-schema FK machinery
(``persistence.cross_schema_foreign_keys``) exists for a real, narrower
need (``run_manifest_id``) this column does not share.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(schema="notification")

notification_deliveries = sa.Table(
    "notification_deliveries",
    metadata,
    sa.Column("delivery_id", sa.Text, primary_key=True),
    sa.Column("notification_type", sa.Text, nullable=False),
    sa.Column("channel", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("workflow_id", sa.Text, nullable=True),
    sa.Column("trace_id", sa.Text, nullable=True),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_notification_deliveries_workflow_id", notification_deliveries.c.workflow_id)
sa.Index("ix_notification_deliveries_status", notification_deliveries.c.status)
