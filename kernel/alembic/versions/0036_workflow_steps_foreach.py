"""Widen workflow_steps.ck_workflow_steps_step_type to include 'foreach'.

Revision ID: 0036_workflow_steps_foreach
Revises: 0035_llm_calls_created_at
Create Date: 2026-08-09

``StepType`` gained an eighth real member, ``FOREACH``
(`P08-S02-M30-T01`, ADR-0021's own "dynamic decomposition without
dynamic control flow" pattern) — see
:mod:`ai_os_kernel.workflow_engine.step_executor`'s own
``ForeachStepExecutor`` for the real executor this unblocks. This
table's own ``ck_workflow_steps_step_type`` (`0002_workflow_steps`) was
built from the exact same seven-member ``_STEP_TYPES`` tuple
:mod:`ai_os_kernel.persistence.schema` still declares — a real,
discovered gap: without this migration, the very first genuinely
persisted ``foreach`` step (success or failure) raises a Postgres
``CheckViolationError``, caught only by attempting a real end-to-end
run against a real database (never surfaced by ``mypy``/unit tests with
fakes).

Drop-and-recreate, the only way to widen a named ``CHECK`` constraint's
own value list in place — no data migration needed, since no row using
the new value can exist before this constraint permits it.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036_workflow_steps_foreach"
down_revision: str | None = "0035_llm_calls_created_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STEP_TYPES = (
    "agent",
    "tool",
    "decision",
    "parallel",
    "sub_workflow",
    "quality_gate",
    "human_approval",
)
_NEW_STEP_TYPES = (*_OLD_STEP_TYPES, "foreach")


def upgrade() -> None:
    op.drop_constraint(
        "ck_workflow_steps_step_type", "workflow_steps", schema="workflow", type_="check"
    )
    op.create_check_constraint(
        "ck_workflow_steps_step_type",
        "workflow_steps",
        "step_type IN (" + ", ".join(f"'{t}'" for t in _NEW_STEP_TYPES) + ")",
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_workflow_steps_step_type", "workflow_steps", schema="workflow", type_="check"
    )
    op.create_check_constraint(
        "ck_workflow_steps_step_type",
        "workflow_steps",
        "step_type IN (" + ", ".join(f"'{t}'" for t in _OLD_STEP_TYPES) + ")",
        schema="workflow",
    )
