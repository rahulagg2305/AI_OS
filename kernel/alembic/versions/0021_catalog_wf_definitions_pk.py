"""Migrate catalog.workflow_definitions to a composite primary key.

Revision ID: 0021_catalog_wf_definitions_pk
Revises: 0020_evaluation_llm_calls
Create Date: 2026-07-26

Changes ``catalog.workflow_definitions``' primary key from the original
single-column ``definition_id`` (created in ``0008_catalog_wf_definitions``)
to the composite ``(definition_id, version)`` now documented in
data_model.md §5, per the approved ``definition_id`` versioning
resolution: ``definition_id`` is stable across every version of a
definition, ``version`` is the separate, varying part, and uniqueness is
on the pair — not ``definition_id`` alone. See
:mod:`ai_os_kernel.persistence.catalog_schema`'s own docstring for the
full reasoning.

**Why a single, atomic ALTER rather than an expand/migrate/contract
sequence** (data_model.md §12 Migration Rule 2 governs backward-incompatible
changes to *populated* tables): this table has no writer anywhere in
this codebase yet (`ManifestLoader` only reads/validates a manifest
file; it does not persist one), so there is no live data to migrate,
dual-write, or backfill. This is also a **strictly safe** primary-key
change independent of that fact: a single-column ``definition_id``
primary key already guarantees every ``definition_id`` value is unique
on its own, and a value unique on one column is trivially still unique
on that column plus another — so no row that could exist under the old
constraint could ever violate the new, strictly broader composite one.
An expand/migrate/contract dance would add process without addressing
any actual risk here.

**Reversibility note**: the downgrade path recreates the original
single-column primary key. This is safe only if no row was inserted
with a duplicate ``definition_id`` (distinguished only by ``version``)
while the composite key was in effect — the entire reason this
migration exists. Downgrading after such a row exists would fail with a
duplicate-key error, which is the expected, correct behaviour: the old
constraint genuinely cannot represent that data anymore.

Two migrations implement this retrofit, deliberately kept separate and
each independently reversible: this one changes the primary key itself;
the next (``0022_workflow_definition_fk``) adds the composite foreign
key from ``workflow.workflow_instances`` against it.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_catalog_wf_definitions_pk"
down_revision: str | None = "0020_evaluation_llm_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_PK_NAME = "workflow_definitions_pkey"
_NEW_PK_NAME = "pk_workflow_definitions"


def upgrade() -> None:
    op.drop_constraint(
        _OLD_PK_NAME,
        "workflow_definitions",
        schema="catalog",
        type_="primary",
    )
    op.create_primary_key(
        _NEW_PK_NAME,
        "workflow_definitions",
        ["definition_id", "version"],
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_constraint(
        _NEW_PK_NAME,
        "workflow_definitions",
        schema="catalog",
        type_="primary",
    )
    op.create_primary_key(
        _OLD_PK_NAME,
        "workflow_definitions",
        ["definition_id"],
        schema="catalog",
    )
