"""Add evaluation.llm_calls.

Revision ID: 0020_evaluation_llm_calls
Revises: 0019_evaluation_metrics
Create Date: 2026-07-26

Creates ``evaluation.llm_calls`` per docs/08_database/data_model.md §6 —
the sixth and last of the six `evaluation` tables (`run_manifests`,
`experiment_runs`, `experiments`, `gate_results`, `metrics` came first).
This completes the `evaluation` schema. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.evaluation_schema` — see that module's
docstring for the full reasoning.

`cost_usd` is `NUMERIC(18, 6)` and `agent_id`/`prompt_id` get real
foreign keys to `catalog.agents.agent_id`/`catalog.prompts.prompt_id` —
the documentation decisions that previously blocked this table, approved
and recorded in data_model.md §6 in a prior documentation-only step.
`workflow_id` gets a real foreign key to `workflow.workflow_instances`,
mirroring every other `evaluation` table's own `workflow_id`. `step_id`
gets none, the identical reason `workflow_events.step_id`/
`approvals.step_id`/`gate_results.step_id` carry none.

Schema and migration only — no writer. No LLM Gateway exists yet to
produce a call to record.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0020_evaluation_llm_calls"
down_revision: str | None = "0019_evaluation_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("call_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column(
            "agent_id",
            sa.Text,
            sa.ForeignKey("catalog.agents.agent_id"),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            sa.Text,
            sa.ForeignKey("catalog.prompts.prompt_id"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("model_alias", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.BigInteger, nullable=False),
        sa.Column("output_tokens", sa.BigInteger, nullable=False),
        sa.Column("cache_read_tokens", sa.BigInteger, nullable=False),
        sa.Column("cache_write_tokens", sa.BigInteger, nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("stop_reason", sa.Text, nullable=False),
        sa.Column("retries", sa.Integer, nullable=False),
        sa.Column("fallback_used", sa.Boolean, nullable=False),
        sa.Column("degradations", JSONB, nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_llm_calls_workflow_id",
        "llm_calls",
        ["workflow_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_llm_calls_agent_id",
        "llm_calls",
        ["agent_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_llm_calls_prompt_id",
        "llm_calls",
        ["prompt_id"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("llm_calls", schema="evaluation")
