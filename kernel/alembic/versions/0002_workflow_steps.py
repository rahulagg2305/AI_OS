"""Add workflow_steps: materialised per-step state.

Revision ID: 0002_workflow_steps
Revises: 0001_workflow_state_baseline
Create Date: 2026-07-25

Creates ``workflow.workflow_steps`` per docs/08_database/data_model.md
§4.3. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.schema` — see that module's docstring
for why ``status`` deliberately has no ``CHECK`` constraint here while
``step_type`` does.

Adds one index beyond what data_model.md §4.3 explicitly lists (which,
unlike §4.1/§4.2, gives no "Indexes:" line for this table at all):
``workflow_id``, the natural per-instance lookup column, mirroring how
every other workflow-state table already indexes its own foreign key
into ``workflow_instances``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0002_workflow_steps"
down_revision: str | None = "0001_workflow_state_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STEP_TYPES = (
    "agent",
    "tool",
    "decision",
    "parallel",
    "sub_workflow",
    "quality_gate",
    "human_approval",
)


def upgrade() -> None:
    op.create_table(
        "workflow_steps",
        sa.Column("step_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("step_name", sa.Text, nullable=False),
        sa.Column("step_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("tool_id", sa.Text, nullable=True),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("usage", JSONB, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "step_type IN (" + ", ".join(f"'{t}'" for t in _STEP_TYPES) + ")",
            name="ck_workflow_steps_step_type",
        ),
        sa.UniqueConstraint(
            "workflow_id",
            "step_name",
            "attempt",
            name="uq_workflow_steps_workflow_id_step_name_attempt",
        ),
        schema="workflow",
    )
    op.create_index(
        "ix_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"], schema="workflow"
    )


def downgrade() -> None:
    op.drop_table("workflow_steps", schema="workflow")
