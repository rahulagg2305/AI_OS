"""Add evaluation.gate_results.created_at.

Revision ID: 0038_gate_results_created_at
Revises: 0037_approvals_decided_at_index
Create Date: 2026-08-13

`api_architecture.md` §6.4's `GET /gates/trends` ("Pass/fail over time")
was blocked on a schema decision, not on effort: `gate_results` has no
timestamp column at all, so there is nothing to bucket a trend by. The
exact same gap, on a sibling table, was already closed the same way by
`0035_llm_calls_created_at` — this migration is that precedent applied,
not a new pattern.

Two alternatives were considered against real code and rejected (product
owner, 2026-08-13). Joining `workflow_instances` for a timestamp needs
no migration but yields the *workflow's* time, and `completed_at` is
NULL for exactly the runs a blocking gate failure halted — the most
interesting rows in a pass/fail trend. Decoding the ULID already
embedded in `result_id` (the code trusts its time-ordering for keyset
pagination today) gives the true gate time with no migration, but a ULID
cannot be time-bucketed in SQL, so every request would have to read the
whole table and aggregate in Python.

Real, additive, backfill-safe: existing rows get `now()` — the
migration's own execution time, not a fabricated historical value, the
identical honest choice `0035` documents for the same situation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038_gate_results_created_at"
down_revision: str | None = "0037_approvals_decided_at_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gate_results",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="evaluation",
    )
    op.create_index(
        "ix_gate_results_created_at",
        "gate_results",
        ["created_at"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_index("ix_gate_results_created_at", table_name="gate_results", schema="evaluation")
    op.drop_column("gate_results", "created_at", schema="evaluation")
