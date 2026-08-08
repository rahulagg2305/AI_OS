"""Add notification.notification_deliveries: real, persisted delivery
status recording for the Notification Service.

Revision ID: 0034_notification_deliveries
Revises: 0033_context_assemblies
Create Date: 2026-08-08

Column-for-column mirror of :mod:`ai_os_kernel.notification.schema` —
see that module's own docstring for the full reasoning. Closes a real,
disclosed gap `P06-S05-M22-T01` left open: every real delivery attempt
was only ever logged (``notification.delivery_attempted``), never
durably recorded (notification_service.md §8: "Delivery status ...
should record ... Timestamp and correlation IDs").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0034_notification_deliveries"
down_revision: str | None = "0033_context_assemblies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")

    op.create_table(
        "notification_deliveries",
        sa.Column("delivery_id", sa.Text, primary_key=True),
        sa.Column("notification_type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("workflow_id", sa.Text, nullable=True),
        sa.Column("trace_id", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="notification",
    )
    op.create_index(
        "ix_notification_deliveries_workflow_id",
        "notification_deliveries",
        ["workflow_id"],
        schema="notification",
    )
    op.create_index(
        "ix_notification_deliveries_status",
        "notification_deliveries",
        ["status"],
        schema="notification",
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries", schema="notification")
    op.execute("DROP SCHEMA IF EXISTS notification")
