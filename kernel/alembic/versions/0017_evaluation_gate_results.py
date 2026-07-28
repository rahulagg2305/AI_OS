"""Add evaluation.gate_results.

Revision ID: 0017_evaluation_gate_results
Revises: 0016_experiment_runs_exp_fk
Create Date: 2026-07-26

Creates ``evaluation.gate_results`` per docs/08_database/data_model.md
§6 — the fourth of the six `evaluation` tables (`run_manifests`,
`experiment_runs`, `experiments` came first). `metrics` and `llm_calls`
remain undocumented-scope for this step; `metrics` specifically is
deferred a third time (its `metric_value numeric` column has no
documented precision/scale). `llm_calls` was evaluated as an alternative
and found to need more invented judgment calls (an untyped `cost_usd`
column, and two id columns that could now technically FK to `catalog`
tables) — `gate_results` has neither gap. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.evaluation_schema` — see that module's
docstring for the full reasoning.

``workflow_id`` gets a real foreign key to ``workflow.workflow_instances``,
mirroring every other `evaluation` table's own `workflow_id`. `step_id`,
`gate_id`, and `gate_version` get none: `step_id` for the same reason
`workflow_events.step_id`/`approvals.step_id` carry none, `gate_id`/
`gate_version` because no Quality Gate Engine or gate-registry table
exists yet.

Schema and migration only — no writer. No Quality Gate Engine exists yet
to produce a gate result.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0017_evaluation_gate_results"
down_revision: str | None = "0016_experiment_runs_exp_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate_results",
        sa.Column("result_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("gate_id", sa.Text, nullable=False),
        sa.Column("gate_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("messages", JSONB, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_gate_results_workflow_id",
        "gate_results",
        ["workflow_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_gate_results_status",
        "gate_results",
        ["status"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("gate_results", schema="evaluation")
