"""Add evaluation.metrics.

Revision ID: 0019_evaluation_metrics
Revises: 0018_catalog_packs
Create Date: 2026-07-26

Creates ``evaluation.metrics`` per docs/08_database/data_model.md §6 —
the fifth of the six `evaluation` tables (`run_manifests`,
`experiment_runs`, `experiments`, `gate_results` came first). Only
`llm_calls` remains undocumented-scope for this step. Column-for-column
mirror of :mod:`ai_os_kernel.persistence.evaluation_schema` — see that
module's docstring for the full reasoning.

`metric_value` is `NUMERIC(20, 6)` — the documentation decision that
previously blocked this table, approved and recorded in data_model.md
§6 in a prior documentation-only step.

`workflow_id` gets a real foreign key to `workflow.workflow_instances`,
mirroring every other `evaluation` table's own `workflow_id`. `run_id`
gets none: retrofitting it against `evaluation.experiment_runs.run_id`
(which now exists) is a distinct, later step, not part of this one's
approved scope.

`recorded_at` has no server default — application-supplied, the same
deliberate divergence from the general "database-generated" timestamp
convention already used for `workflow.workflow_events.occurred_at` and
`governance.audit_log.occurred_at`.

Schema and migration only — no writer. No Evaluation Engine exists yet
to produce a metric.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_evaluation_metrics"
down_revision: str | None = "0018_catalog_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("metric_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("metric_name", sa.Text, nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("source_component", sa.Text, nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_metrics_workflow_id",
        "metrics",
        ["workflow_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_metrics_run_id",
        "metrics",
        ["run_id"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("metrics", schema="evaluation")
