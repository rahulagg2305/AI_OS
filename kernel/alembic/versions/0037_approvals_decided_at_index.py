"""Add ix_approvals_decided_at: keyset pagination support for
api_architecture.md §6.2's own documented GET /api/v1/approvals/history.

Revision ID: 0037_approvals_decided_at_index
Revises: 0036_workflow_steps_foreach
Create Date: 2026-08-10

`P06-S04-M38-T01` (revisited) closes the last of the 4 documented
Approvals endpoints — "Past decisions" ("GET /api/v1/approvals/history").
Unlike the pending queue (`list_pending`, genuinely small and bounded,
deliberately unpaginated), decided approvals accumulate for the life
of the platform, so this needs the same real, cursor-paginated shape
`GET /workflows` already established, not a speculative unpaginated
list. `ix_approvals_decided_at` on `(decided_at, approval_id)` backs
the identical composite `< (decided_at, approval_id)` keyset comparison
`ix_workflow_instances_created_at_desc` already backs for
`list_instances` — real index, not a hopeful query without one.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037_approvals_decided_at_index"
down_revision: str | None = "0036_workflow_steps_foreach"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_approvals_decided_at",
        "approvals",
        ["decided_at", "approval_id"],
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_index("ix_approvals_decided_at", table_name="approvals", schema="workflow")
