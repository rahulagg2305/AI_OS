"""Add workflow_instances.scheduled_at.

Revision ID: 0032_scheduled_at
Revises: 0031_principal_permissions
Create Date: 2026-08-03

The Scheduler's own data (workflow_architecture.md §5.13 / §5.13
functional_requirements.md: "Supports delayed and scheduled workflow
starts") — workflow_engine.md's own Implementation Status named this
component as "not built at all" until this step.

**Nullable, mirroring ``principal_permissions``'s own "optional, not
every instance has one" shape.** ``NULL`` means "no scheduled start was
requested" — every real caller before this step (``P02-S01-M05-T13``), and every
``create`` call that still omits the new keyword, is unaffected: such
an instance is created exactly as before and must still be started by
an explicit ``start()`` call. A non-``NULL`` value means "genuinely
start this instance no earlier than this real timestamp" —
:class:`~ai_os_kernel.workflow_engine.scheduler.WorkflowScheduler` is
the one real reader.

Purely additive (one nullable column) — safe regardless of existing
data, no migrate/backfill step needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_scheduled_at"
down_revision: str | None = "0031_principal_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_instances",
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_column("workflow_instances", "scheduled_at", schema="workflow")
