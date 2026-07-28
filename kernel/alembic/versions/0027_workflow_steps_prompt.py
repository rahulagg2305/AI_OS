"""Add workflow_steps.prompt_id/prompt_version/model_alias.

Revision ID: 0027_workflow_steps_prompt
Revises: 0026_metrics_run_id_fk
Create Date: 2026-07-26

Adds three nullable columns to ``workflow.workflow_steps`` — the same
table's ``agent_id``/``tool_id`` precedent, extended to the remaining
three fields of workflow_architecture.md's Step Contract:
``promptId``/``promptVersion``/``modelAlias``, both `agent`-step-only
and optional even there. Typed ``sa.Text`` for all three, matching
``evaluation.llm_calls.prompt_id``/``prompt_version``/``model_alias``
exactly (data_model.md §6) — the closest existing precedent for this
shape.

**Deliberately no foreign key on ``prompt_id``/``prompt_version``**,
unlike ``evaluation.llm_calls``' own composite foreign key to
``catalog.prompts (prompt_id, version)``. That FK is safe on
``llm_calls`` because a real call actually happened against a real,
already-rendered prompt. Here, ``prompt_id``/``prompt_version`` merely
record what a step *declared* in its definition — no writer exists for
`catalog.prompts` in this codebase (only a reader, `SqlPromptCatalog`),
so a real FK would make it impossible to ever record a declared
`prompt_id` that has no matching catalog row yet, the identical failure
mode already learned from the `workflow_definitions` FK saga (a real FK
is only safe once a genuine writer for the target exists and is
exercised — not the case here). ``agent_id``/``tool_id`` on this same
table carry no foreign key for the identical reason (no writer for
``catalog.agents``/``catalog.tools`` either); this keeps the new columns
consistent with their two existing siblings, not a fresh exception.

No new index: `agent_id`/`tool_id` are not individually indexed either
(only `workflow_id` is) — the same precedent extended to these three
columns, not a fresh decision.

This migration is purely additive (three nullable columns) — safe
regardless of existing data, no migrate/backfill step needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_workflow_steps_prompt"
down_revision: str | None = "0026_metrics_run_id_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_steps",
        sa.Column("prompt_id", sa.Text, nullable=True),
        schema="workflow",
    )
    op.add_column(
        "workflow_steps",
        sa.Column("prompt_version", sa.Text, nullable=True),
        schema="workflow",
    )
    op.add_column(
        "workflow_steps",
        sa.Column("model_alias", sa.Text, nullable=True),
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_column("workflow_steps", "model_alias", schema="workflow")
    op.drop_column("workflow_steps", "prompt_version", schema="workflow")
    op.drop_column("workflow_steps", "prompt_id", schema="workflow")
