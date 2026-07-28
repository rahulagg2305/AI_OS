"""Migrate catalog.prompts to a composite primary key + retrofit the
evaluation.llm_calls prompt foreign key.

Revision ID: 0024_catalog_prompts_pk
Revises: 0023_workflow_definition_fk
Create Date: 2026-07-26

Changes ``catalog.prompts``' primary key from the original single-column
``prompt_id`` (created in ``0009_catalog_prompts``) to the composite
``(prompt_id, version)`` now documented in data_model.md §5 — the
identical situation ``catalog.workflow_definitions`` was already in
(``0021_catalog_wf_definitions_pk``): a single-column ``prompt_id``
primary key made it impossible to store two versions of the same prompt
as separate rows, even though "versions are immutable — a change
creates a new version row" (data_model.md §5) already implied multiple
rows must be possible. Discovered while building a second
``PromptEngine`` implementation
(:class:`ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`) against
this table.

**Why a single, atomic ALTER rather than an expand/migrate/contract
sequence**: identical reasoning to ``0021_catalog_wf_definitions_pk`` —
this table has no writer anywhere in this codebase (only readers:
:class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog` and the
test fixtures that seed rows directly), so there is no live data to
migrate, dual-write, or backfill. The primary-key change is also safe
by construction independent of that fact: a single-column ``prompt_id``
primary key already guarantees every ``prompt_id`` value is unique on
its own, and a value unique on one column is trivially still unique on
that column plus another — so no row that could exist under the old
constraint could ever violate the new, strictly broader composite one.

**Unlike the ``workflow_definitions`` precedent, this migration cannot
be split into "change the primary key" and "add the foreign key" as two
separate, independently-reversible steps** (``0021``/``0023`` were split
that way only because the foreign key did not exist yet when the
primary key changed). Here, ``evaluation.llm_calls.prompt_id`` already
carries a **live** single-column foreign key to ``catalog.prompts.
prompt_id`` (added in ``0020_evaluation_llm_calls``) — Postgres refuses
to drop a primary key while a foreign key still depends on it, so the
old foreign key must be dropped first, in the same migration, and the
table would be left with no referential integrity on ``prompt_id`` at
all if the replacement composite foreign key were deferred to a later
migration. All four steps — drop the old FK, drop the old PK, create
the new composite PK, create the new composite FK — are therefore one
atomic, reversible unit.

**The new composite foreign key is also a genuine correctness
improvement, not just a mechanical necessity**: the old single-column
foreign key only checked that ``prompt_id`` existed *somewhere* in
``catalog.prompts``, never that ``prompt_version`` matched the actual
``version`` of that row. Verified safe against every existing caller
before writing this migration: ``SqlLLMCallRecorder`` always echoes
``prompt_id``/``prompt_version`` straight from a caller-supplied pair
that itself came from a real render (see
:mod:`ai_os_kernel.llm_gateway.call_recorder`), and every existing
integration test that seeds both ``catalog.prompts`` and
``evaluation.llm_calls`` rows already uses a matching ``version``/
``prompt_version`` pair (checked directly against
``tests/integration/llm_gateway/test_call_recorder.py`` and
``tests/integration/persistence/test_migrations.py`` before writing
this migration) — confirmed by running the full test suite with this
migration in place, not assumed.

**Reversibility note**: the downgrade path recreates the original
single-column primary key and single-column foreign key. Safe only if
no row was inserted with a duplicate ``prompt_id`` (distinguished only
by ``version``) while the composite key was in effect — the entire
reason this migration exists. Downgrading after such a row exists would
fail with a duplicate-key error, the expected, correct behaviour.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_catalog_prompts_pk"
down_revision: str | None = "0023_workflow_definition_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_PK_NAME = "prompts_pkey"
_NEW_PK_NAME = "pk_prompts"
_OLD_FK_NAME = "llm_calls_prompt_id_fkey"
_NEW_FK_NAME = "fk_llm_calls_prompt_id_version"


def upgrade() -> None:
    # The old FK must go first: Postgres refuses to drop a primary key
    # that a foreign key still depends on.
    op.drop_constraint(
        _OLD_FK_NAME,
        "llm_calls",
        schema="evaluation",
        type_="foreignkey",
    )
    op.drop_constraint(
        _OLD_PK_NAME,
        "prompts",
        schema="catalog",
        type_="primary",
    )
    op.create_primary_key(
        _NEW_PK_NAME,
        "prompts",
        ["prompt_id", "version"],
        schema="catalog",
    )
    op.create_foreign_key(
        _NEW_FK_NAME,
        "llm_calls",
        "prompts",
        ["prompt_id", "prompt_version"],
        ["prompt_id", "version"],
        source_schema="evaluation",
        referent_schema="catalog",
    )


def downgrade() -> None:
    op.drop_constraint(
        _NEW_FK_NAME,
        "llm_calls",
        schema="evaluation",
        type_="foreignkey",
    )
    op.drop_constraint(
        _NEW_PK_NAME,
        "prompts",
        schema="catalog",
        type_="primary",
    )
    op.create_primary_key(
        _OLD_PK_NAME,
        "prompts",
        ["prompt_id"],
        schema="catalog",
    )
    op.create_foreign_key(
        _OLD_FK_NAME,
        "llm_calls",
        "prompts",
        ["prompt_id"],
        ["prompt_id"],
        source_schema="evaluation",
        referent_schema="catalog",
    )
