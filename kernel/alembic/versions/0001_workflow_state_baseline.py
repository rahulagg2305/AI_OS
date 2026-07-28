"""Workflow state baseline: workflow_instances, workflow_events, workflow_leases.

Revision ID: 0001_workflow_state_baseline
Revises:
Create Date: 2026-07-25

Creates exactly the three tables approved for the Stage B persistence-
foundation step, per docs/08_database/data_model.md §4.1, §4.2, §4.4 and
ADR-0011. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.schema` — see that module's docstring for
the two documented details deliberately deferred (the application-role
UPDATE/DELETE revocation on workflow_events, and the not-yet-existing
catalog/evaluation foreign keys).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_workflow_state_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INSTANCE_STATUSES = (
    "created",
    "running",
    "waiting_for_human",
    "waiting_for_retry",
    "quality_gate_failed",
    "compensating",
    "completed",
    "failed",
    "cancelled",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS workflow")

    op.create_table(
        "workflow_instances",
        sa.Column("workflow_id", sa.Text, primary_key=True),
        sa.Column("definition_id", sa.Text, nullable=False),
        sa.Column("definition_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("current_step_id", sa.Text, nullable=True),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=True),
        sa.Column("experiment_id", sa.Text, nullable=True),
        sa.Column("run_manifest_id", sa.Text, nullable=True),
        sa.Column("principal_id", sa.Text, nullable=False),
        sa.Column("last_event_seq", sa.BigInteger, nullable=False),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in _INSTANCE_STATUSES) + ")",
            name="ck_workflow_instances_status",
        ),
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_instances_status", "workflow_instances", ["status"], schema="workflow"
    )
    op.create_index(
        "ix_workflow_instances_definition_id",
        "workflow_instances",
        ["definition_id"],
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_instances_experiment_id",
        "workflow_instances",
        ["experiment_id"],
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_instances_created_at_desc",
        "workflow_instances",
        [sa.text("created_at DESC")],
        schema="workflow",
    )

    op.create_table(
        "workflow_events",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("trace_id", sa.Text, nullable=True),
        sa.Column("step_id", sa.Text, nullable=True),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_id", "seq", name="uq_workflow_events_workflow_id_seq"),
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_events_event_type", "workflow_events", ["event_type"], schema="workflow"
    )
    op.create_index(
        "ix_workflow_events_occurred_at_desc",
        "workflow_events",
        [sa.text("occurred_at DESC")],
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_events_trace_id", "workflow_events", ["trace_id"], schema="workflow"
    )

    op.create_table(
        "workflow_leases",
        sa.Column("lease_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("worker_id", sa.Text, nullable=False),
        sa.Column("acquired_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_table("workflow_leases", schema="workflow")
    op.drop_table("workflow_events", schema="workflow")
    op.drop_table("workflow_instances", schema="workflow")
    op.execute("DROP SCHEMA IF EXISTS workflow")
