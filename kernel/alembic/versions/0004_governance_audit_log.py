"""Add governance.audit_log: append-only, hash-chained audit log.

Revision ID: 0004_governance_audit_log
Revises: 0003_approvals
Create Date: 2026-07-26

Creates ``governance.audit_log`` per docs/08_database/data_model.md
§9.1. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.governance_schema` — see that module's
docstring for the reasoning behind ``outcome`` getting a ``CHECK``
constraint while ``event_type`` does not, the ``Identity()`` column for
the documented ``bigserial``, and why there is no foreign key.

Schema and migration only — no writer. ADR-0017's tamper-evident,
hash-chained audit path is deliberately separate from the OTLP
telemetry path (:mod:`ai_os_kernel.observability`); nothing computes
``row_hash``/``prev_hash`` or writes a row here yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0004_governance_audit_log"
down_revision: str | None = "0003_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_OUTCOMES = (
    "allowed",
    "denied",
    "success",
    "failure",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS governance")

    op.create_table(
        "audit_log",
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
        schema="governance",
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"], schema="governance")
    op.create_index(
        "ix_audit_log_occurred_at_desc",
        "audit_log",
        [sa.text("occurred_at DESC")],
        schema="governance",
    )
    op.create_index("ix_audit_log_trace_id", "audit_log", ["trace_id"], schema="governance")


def downgrade() -> None:
    op.drop_table("audit_log", schema="governance")
    op.execute("DROP SCHEMA IF EXISTS governance")
