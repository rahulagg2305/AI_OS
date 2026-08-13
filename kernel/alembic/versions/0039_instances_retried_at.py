"""Add workflow.workflow_instances.retried_at.

Revision ID: 0039_instances_retried_at
Revises: 0038_gate_results_created_at
Create Date: 2026-08-13

`POST /api/v1/workflows/{id}/retry` (`api_architecture.md` §6.1, "Retry
from last failure") needs a **retry epoch**, and the reason is specific
rather than general bookkeeping.

`WorkflowWorkerLoop._fail_if_retries_exhausted` (`P02-S01-M05-T17`,
R-016) computes its bound from `workflow_steps` rows where
`status = 'failed'`, on both axes `error_handling_retry.md` §4 requires:
`count(*)` against `max_attempts`, and `now() - min(started_at)` against
`max_duration_seconds`, exhausted when *either* is spent. A `failed`
instance has by definition already spent both. So a retry that merely
flipped the status back to `running` would grant exactly **one** further
attempt no matter what the definition declares — `min(started_at)` is by
then far older than `max_duration_seconds` (60s by default), so the
first new failure would immediately re-fail the instance.

Product-owner decision, 2026-08-13: an operator retry grants a genuinely
**fresh** budget, so the definition's declared `retryPolicy` keeps
meaning on the retry path too. `step_failure_stats` counts only failures
at or after `retried_at`. Two alternatives were declined: one-more-
attempt (the declared policy would have no effect at all on this path),
and relabelling the old `failed` step rows (a fresh budget with no
migration, but it rewrites already-written history and leaks an
undeclared status to `GET /workflows/{id}/steps`).

Nullable with no default and no backfill, deliberately: `NULL` means
"never retried", which is the honest state of every row that exists
today, and the filter treats it as "count every failure" — exactly the
pre-existing behaviour. No index: this column is only ever read by
`workflow_id`, already the primary key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# Kept under 32 characters: alembic's own `alembic_version.version_num`
# is `varchar(32)`, and a longer id fails the upgrade at runtime with a
# bare StringDataRightTruncationError. Found by running the migration,
# not by reading it.
revision: str = "0039_instances_retried_at"
down_revision: str | None = "0038_gate_results_created_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_instances",
        sa.Column("retried_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_column("workflow_instances", "retried_at", schema="workflow")
