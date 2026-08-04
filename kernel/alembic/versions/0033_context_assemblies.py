"""Add context.context_assemblies: real, persisted context-assembly
audit records.

Revision ID: 0033_context_assemblies
Revises: 0032_scheduled_at
Create Date: 2026-08-04

Column-for-column mirror of :mod:`ai_os_kernel.context_manager.schema`
— see that module's own docstring, and docs/08_database/data_model.md
§9b, for the full reasoning.

Closes a real, previously-disclosed gap: context_manager.md §9's own
audit record had no schema to write to at all — `assembly_id` was
generated per call but never durably stored, so exact replay of a past
assembly was not possible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0033_context_assemblies"
down_revision: str | None = "0032_scheduled_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS context")

    op.create_table(
        "context_assemblies",
        sa.Column("assembly_id", sa.Text, primary_key=True),
        sa.Column("workflow_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("sources_queried", JSONB, nullable=False),
        sa.Column("included_items", JSONB, nullable=False),
        sa.Column("items_excluded_count", sa.Integer, nullable=False),
        sa.Column("total_tokens", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="context",
    )
    op.create_index(
        "ix_context_assemblies_workflow_id",
        "context_assemblies",
        ["workflow_id"],
        schema="context",
    )
    op.create_index(
        "ix_context_assemblies_recorded_at_desc",
        "context_assemblies",
        [sa.text("recorded_at DESC")],
        schema="context",
    )


def downgrade() -> None:
    op.drop_table("context_assemblies", schema="context")
    op.execute("DROP SCHEMA IF EXISTS context")
