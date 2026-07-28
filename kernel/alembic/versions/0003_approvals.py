"""Add approvals: human approval decisions.

Revision ID: 0003_approvals
Revises: 0002_workflow_steps
Create Date: 2026-07-25

Creates ``workflow.approvals`` per docs/08_database/data_model.md §4.5.
Column-for-column mirror of :mod:`ai_os_kernel.persistence.schema` —
see that module's docstring for the nullability reasoning (drawn from
the already-established Human Approval Point Contract,
`ai_os_kernel.workflow_engine.models.HumanApprovalPoint`) and for why
this table is named ``approvals``, not ``workflow_approvals`` (data_model
.md §4.5's own header does not repeat the schema name in the table name,
unlike every other table in this schema).

Schema and migration only — no writer. No Human Approval Point
execution path exists yet to populate this table (agent/tool/LLM work,
out of scope here).

Adds two indexes beyond what data_model.md §4.5 explicitly lists (which,
like §4.3, gives no "Indexes:" line at all): ``workflow_id`` (the
natural per-instance lookup, mirroring every other workflow-state
table) and ``status`` (mirroring ``workflow_instances.status``'s own
index — "all pending approvals" is as natural an operational query as
"all running instances").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0003_approvals"
down_revision: str | None = "0002_workflow_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPROVAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "changes_requested",
    "timed_out",
    "cancelled",
)


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("approval_class", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("context_digest", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("decided_by", sa.Text, nullable=True),
        sa.Column("decision_comment", sa.Text, nullable=True),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in _APPROVAL_STATUSES) + ")",
            name="ck_approvals_status",
        ),
        schema="workflow",
    )
    op.create_index("ix_approvals_workflow_id", "approvals", ["workflow_id"], schema="workflow")
    op.create_index("ix_approvals_status", "approvals", ["status"], schema="workflow")


def downgrade() -> None:
    op.drop_table("approvals", schema="workflow")
