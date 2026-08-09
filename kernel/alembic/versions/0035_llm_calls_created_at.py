"""Add evaluation.llm_calls.created_at.

Revision ID: 0035_llm_calls_created_at
Revises: 0034_notification_deliveries
Create Date: 2026-08-09

`P07-S03-M42-T02` (Cost Anomaly Alerting, NFR-045: "Fires within 5
minutes when hourly spend exceeds 3x the trailing 7-day hourly mean")
found `llm_calls` has no timestamp column at all — no way to bucket
spend by hour without one. Real, additive, backfill-safe: existing
rows get `now()` (the migration's own execution time, not a
fabricated historical value — see `data_model.md` §6's own note).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035_llm_calls_created_at"
down_revision: str | None = "0034_notification_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="evaluation",
    )
    op.create_index(
        "ix_llm_calls_created_at",
        "llm_calls",
        ["created_at"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls", schema="evaluation")
    op.drop_column("llm_calls", "created_at", schema="evaluation")
