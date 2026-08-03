"""Add workflow_instances.principal_permissions.

Revision ID: 0031_principal_permissions
Revises: 0030_security_role_grants
Create Date: 2026-08-03

The principal term of ADR-0023's monotonic-narrowing chain
(:mod:`ai_os_kernel.security_manager.narrowing`), captured once at
workflow-trigger time and read back at agent/tool resolution
(:mod:`ai_os_kernel.workflow_engine.registry`) — see that module's own
docstring for why a snapshot, not a live ``SecurityContext``, is what
travels here: resolution can happen long after the triggering HTTP
request (and its bearer token) has ended, including from a worker-loop
tick with no request in scope at all.

**Nullable, mirroring ``workflow_instances.run_manifest_id``'s own
"optional, not every instance has one" shape — deliberately never a
``NOT NULL`` column with an empty-array default.** ``NULL`` means "no
real ``SecurityContext`` reached this instance's own trigger call, the
principal term is not enforced for it" (every real caller before this
step, and every trigger call that still omits the new keyword). An
empty JSON array would instead mean "this principal holds zero
permissions," which is a completely different, incorrect claim that
would refuse every real agent/tool resolution for that instance.

Purely additive (one nullable column) — safe regardless of existing
data, no migrate/backfill step needed.

**Revision id kept short (26 chars) — deliberately not the fuller
``0031_workflow_instances_principal_permissions``.** Alembic's own
``alembic_version.version_num`` column is ``VARCHAR(32)``; a longer id
was tried first and genuinely failed a real upgrade with
``StringDataRightTruncationError`` — every other revision id in this
tree already stays under that limit, this one now does too.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0031_principal_permissions"
down_revision: str | None = "0030_security_role_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_instances",
        sa.Column("principal_permissions", JSONB, nullable=True),
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_column("workflow_instances", "principal_permissions", schema="workflow")
