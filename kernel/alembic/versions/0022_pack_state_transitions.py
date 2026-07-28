"""Add catalog.pack_state_transitions.

Revision ID: 0022_pack_state_transitions
Revises: 0021_catalog_wf_definitions_pk
Create Date: 2026-07-26

Creates ``catalog.pack_state_transitions`` per docs/08_database/data_model.md
§5 — the sixth and last table §5 documents, completing the `catalog`
schema. Its primary key (``transition_id``) and required foreign key
(``pack_id`` -> ``packs.pack_id``) were approved and recorded in
data_model.md §5 in the same step that implements them here — the
identical "documentation decision recorded, then implemented" sequence
already followed for `catalog.packs`' own primary key. Column-for-column
mirror of :mod:`ai_os_kernel.persistence.catalog_schema` — see that
module's docstring for the full reasoning.

`from_state`/`to_state` get a `CHECK` constraint against the same
eight-value canonical pack lifecycle already enforced on `packs.state`
(`capability_manager.md` §4's single authority for that list) — not a
new list, the same domain a transition necessarily moves between.
`occurred_at` has no server default — application-supplied, the same
deliberate divergence from the general "database-generated" timestamp
convention already used for `workflow_events.occurred_at`/`governance.
audit_log.occurred_at`/`evaluation.metrics.recorded_at`.

Schema and migration only — no writer. No Capability Manager exists yet
to record a pack lifecycle transition.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_pack_state_transitions"
down_revision: str | None = "0021_catalog_wf_definitions_pk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PACK_STATES = (
    "discovered",
    "validated",
    "installed",
    "configured",
    "activated",
    "deactivated",
    "failed",
    "uninstalled",
)


def upgrade() -> None:
    op.create_table(
        "pack_state_transitions",
        sa.Column("transition_id", sa.Text, primary_key=True),
        sa.Column(
            "pack_id",
            sa.Text,
            sa.ForeignKey("catalog.packs.pack_id"),
            nullable=False,
        ),
        sa.Column("from_state", sa.Text, nullable=False),
        sa.Column("to_state", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_state IN (" + ", ".join(f"'{s}'" for s in _PACK_STATES) + ")",
            name="ck_pack_state_transitions_from_state",
        ),
        sa.CheckConstraint(
            "to_state IN (" + ", ".join(f"'{s}'" for s in _PACK_STATES) + ")",
            name="ck_pack_state_transitions_to_state",
        ),
        schema="catalog",
    )
    op.create_index(
        "ix_pack_state_transitions_pack_id",
        "pack_state_transitions",
        ["pack_id"],
        schema="catalog",
    )
    op.create_index(
        "ix_pack_state_transitions_occurred_at_desc",
        "pack_state_transitions",
        [sa.text("occurred_at DESC")],
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_table("pack_state_transitions", schema="catalog")
