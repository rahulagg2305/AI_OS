"""Add platform.event_outbox and platform.idempotency_keys.

Revision ID: 0006_platform_outbox_idempotency
Revises: 0005_governance_config_changes
Create Date: 2026-07-26

Creates ``platform.event_outbox`` and ``platform.idempotency_keys`` per
docs/08_database/data_model.md §10. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.platform_schema` — see that module's
docstring for the reasoning behind ``event_outbox.attempts``' zero
default, why neither table has a foreign key, and why the third table
§10 documents (``platform.schema_metadata``) is deliberately not
created here: §10 gives it no column list at all, only a purpose
description, and inventing one would cross the line every other table
in this persistence layer has held.

Schema and migration only — no writer for either table. ``event_outbox``
is ADR-0012's transactional outbox; nothing writes to it yet, and the
Event Bus itself does not exist yet. ``idempotency_keys`` has no writer
either — no HTTP route yet needs idempotent-replay of a mutating
request.

Revision id kept to 32 characters or fewer: Alembic's own
``alembic_version.version_num`` column defaults to ``VARCHAR(32)``, and
every prior revision id in this chain happened to fit that only by not
having been long enough to test it — this one is exactly at the limit,
named for its content within that constraint.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0006_platform_outbox_idempotency"
down_revision: str | None = "0005_governance_config_changes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")

    op.create_table(
        "event_outbox",
        sa.Column("outbox_id", sa.Text, primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("trace_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        schema="platform",
    )
    op.create_index(
        "ix_event_outbox_dispatched_at", "event_outbox", ["dispatched_at"], schema="platform"
    )
    op.create_index("ix_event_outbox_created_at", "event_outbox", ["created_at"], schema="platform")

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("principal_id", sa.Text, nullable=False),
        sa.Column("request_digest", sa.Text, nullable=False),
        sa.Column("response", JSONB, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="platform",
    )
    op.create_index(
        "ix_idempotency_keys_expires_at",
        "idempotency_keys",
        ["expires_at"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="platform")
    op.drop_table("event_outbox", schema="platform")
    op.execute("DROP SCHEMA IF EXISTS platform")
