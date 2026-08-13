"""Canonical Core table definitions for evaluation persistence.

Mirrors docs/08_database/data_model.md §6, in the same style as
:mod:`ai_os_kernel.persistence.governance_schema`,
:mod:`ai_os_kernel.persistence.platform_schema`,
:mod:`ai_os_kernel.persistence.trace_schema`, and
:mod:`ai_os_kernel.persistence.catalog_schema`: kept in its own module
with its own ``MetaData`` (schema ``evaluation``), a genuinely distinct
bounded context from ``workflow``, ``governance``, ``platform``,
``trace``, and ``catalog``. Combined into ``target_metadata`` in
``kernel/alembic/env.py`` alongside the other five.

All six tables §6 documents are now defined here: ``run_manifests``,
``experiment_runs``, ``experiments``, ``gate_results``, ``metrics``, and
now ``llm_calls`` — the last one, previously deferred twice for needing
more judgment calls (an untyped ``cost_usd``, and two id columns that
could real-FK to ``catalog`` tables) than ``gate_results``/``metrics``
needed at the time. Both gaps are now resolved and recorded in
data_model.md §6 (see ``llm_calls``' own note below), so this module now
covers the full ``evaluation`` schema §6 documents.

This docstring's original "Schema and migration only — no writer for
any of the six" is now stale — **all six tables have a real writer.**
``gate_results``/``run_manifests``/``llm_calls``/``metrics`` gained one
incrementally (see ``evaluation_engine.md``'s own Implementation Status);
``experiments`` gained ``evaluation_engine.experiment_repository.
SqlExperimentRepository`` (``P04-S01-M12-T12``, ``POST /api/v1/
experiments``); and ``experiment_runs`` gained
``sdk_adapters.experiment_run_recorder_adapter.SqlExperimentRunRecorder``
(``P04-S03-M34-T02``). That recorder had **no production caller** until
``evaluation_engine.experiment_run_orchestrator.ExperimentRunOrchestrator``
(``P04-S01-M12-T13``, ``POST /experiments/{id}/run``) became the first —
it must be a caller, not just the writer, because ``experiment_runs``'
own ``workflow_id``/``resolved_model_id``/``served_from_cache`` columns
below are all ``NOT NULL``, so a row can only be written for a workflow
that has genuinely been launched and run. §6 describes ``run_manifests``
as "the complete pinned-conditions bundle required by ADR-0022
(Reproducibility over Determinism)"; ``experiment_runs`` records one
variant/replicate of a running experiment; ``experiments`` is the
experiment definition itself; ``gate_results`` records one Quality Gate
Engine evaluation; ``metrics`` records one measured value produced
somewhere in a workflow run; ``llm_calls`` is "the single authoritative
record of model spend" (§6's own words) for one LLM Gateway call.

``run_manifests`` — column-for-column per §6: ``run_manifest_id`` PK,
``workflow_id``, ``manifest`` (jsonb), ``manifest_hash``. §6 marks no
column nullable, so — the same "explicit `NULL` is the only nullability
signal" convention already followed for every schema added so far — all
four are ``NOT NULL``. ``manifest`` is ``JSONB`` (a structured "bundle",
per data_model.md §2's own JSONB convention for structured payloads);
``manifest_hash`` is a plain text digest, the same role
``governance.audit_log.row_hash``/``catalog.prompts.content_hash`` play
for their own rows. No ``CHECK`` constraint: no enum-like column exists
here.

``experiment_runs`` — column-for-column per §6: ``run_id`` PK,
``experiment_id``, ``workflow_id``, ``variant_key``, ``model_alias``,
``resolved_model_id``, ``replicate_index``, ``served_from_cache`` (bool,
explicitly marked ``NOT NULL`` in §6 itself), ``status``. Every other
column is likewise ``NOT NULL`` (§6 marks none of them nullable either).
``replicate_index`` is ``Integer`` (§6's own text: "``replicate_index``
and ``runs_per_variant`` exist because comparisons must report variance
across repeated runs" — an ordinal count, not a numeric measurement, so
no precision/scale decision is needed the way a ``numeric`` column would
require). Every other column is a plain identifier/label, so ``Text``.
No ``CHECK`` constraint on ``status``: §6 gives it no documented value
list, the same open-ended reasoning already applied to
``workflow_steps.status``/``workflow_events.event_type``.

``experiment_runs`` has **two** foreign keys, added in two different
steps: ``workflow_id`` → :data:`ai_os_kernel.persistence.schema.
workflow_instances.c.workflow_id` (added when this table was created,
target already existed); ``experiment_id`` → ``experiments.c.
experiment_id`` (added below, once ``experiments`` exists in this same
module — see the ``append_constraint`` call after both tables). Unlike
the ``workflow_instances.run_manifest_id`` retrofit (a *different*
schema module, requiring a standalone wiring module to avoid a circular
import — see :mod:`ai_os_kernel.persistence.cross_schema_foreign_keys`),
this one is a same-module, same-``MetaData`` retrofit: trivial, with no
import-ordering hazard, since both tables already live here.

``experiments`` — column-for-column per §6: ``experiment_id`` PK,
``name``, ``description``, ``definition_id``, ``definition_version``,
``variables`` (jsonb — "what is deliberately varied"), ``pinned_conditions``
(jsonb), ``runs_per_variant`` (int, explicitly marked ``NOT NULL`` in §6
itself), ``status``, ``created_by``. Every other column is likewise
``NOT NULL`` (§6 marks none of them nullable). ``variables`` and
``pinned_conditions`` are ``JSONB`` — both are explicitly structured,
per §6's own parenthetical and data_model.md §2's general JSONB
convention. ``runs_per_variant`` is ``Integer`` (a count, the same
reasoning as ``experiment_runs.replicate_index``). Every other column
is a plain identifier/label, so ``Text``. No ``CHECK`` constraint on
``status``: same open-ended reasoning as ``experiment_runs.status``.

**``experiments.definition_id``/``definition_version`` now carry a
composite foreign key** against
:data:`ai_os_kernel.persistence.catalog_schema.workflow_definitions`'s
own composite primary key, ``(definition_id, version)`` — the identical
pattern already established for :data:`ai_os_kernel.persistence.schema.
workflow_instances`'s own ``definition_id``/``definition_version`` pair.
Deliberately deferred when this table was first created (the versioning
ambiguity between this pair and ``catalog.workflow_definitions``' single-
column primary key was still open at the time, and no writer existed to
safely reference); both blockers are now resolved —
:class:`ai_os_kernel.workflow_engine.definition_catalog.
SqlWorkflowDefinitionCatalog` exists, and ``workflow_instances``' own
identical retrofit (``0023_workflow_definition_fk``) is already enforced
and passing — so this table's own retrofit (``0025_experiments_definition_fk``)
follows the same "verify against the full test suite, don't assume"
discipline, not a fresh decision made from scratch.

Neither ``run_manifests`` nor ``experiment_runs`` gets an index beyond
its own foreign key column(s) — §6 has no "Indexes:" line for this
section (unlike §7's knowledge tables). ``experiments`` gets two
indexes beyond its primary key, by the same kind of analogy already
used throughout this persistence layer even without an explicit
"Indexes:" line: ``definition_id`` (the natural "all experiments run
against this workflow definition" query — the same reasoning already
applied to every ``catalog`` table's own ``pack_id`` index, despite
carrying no foreign key either) and ``status`` (the natural "all
running/active experiments" query — the same reasoning already applied
to ``workflow_instances.status``/``approvals.status``).

``gate_results`` — column-for-column per §6: ``result_id`` PK,
``workflow_id``, ``step_id``, ``gate_id``, ``gate_version``, ``status``,
``severity``, ``metrics`` (jsonb), ``messages`` (jsonb), ``duration_ms``.
Every column is ``NOT NULL`` (§6 marks none nullable). ``metrics`` and
``messages`` are ``JSONB``, explicitly marked so in §6 itself.
``duration_ms`` is ``Integer`` — an unambiguous millisecond count, unlike
``metrics.metric_value``'s undocumented ``numeric`` precision/scale, and
exactly why this table was chosen over ``metrics`` for this step. Every
other column is a plain identifier/label, so ``Text``. No ``CHECK``
constraint on ``status`` or ``severity``: §6 gives neither a documented
value list — the same open-ended reasoning already applied to
``workflow_steps.status``/``experiment_runs.status``, deliberately not
extended into inventing a severity taxonomy (e.g. info/warning/error)
that §6 does not state.

``gate_results.workflow_id`` gets the by-now-standard real foreign key
to ``workflow_instances``. ``step_id``, ``gate_id``, and ``gate_version``
get none — ``step_id`` for the identical reason ``workflow_events.step_id``
and ``approvals.step_id`` carry none (no table persists the set of
declared step ids a definition's steps must belong to), and ``gate_id``/
``gate_version`` because no Quality Gate Engine or gate-registry table
exists yet to reference.

Two indexes beyond the primary key, mirroring ``approvals`` — the
closest existing table in shape (also ``workflow_id`` + ``step_id`` +
a lifecycle ``status`` column): ``workflow_id`` (the standard FK index)
and ``status`` (the natural "all failed/pending gate results" query,
the same reasoning already applied to ``workflow_instances.status``/
``approvals.status``). ``step_id`` is deliberately *not* indexed here
either, following ``approvals``' own precedent of leaving its own
``step_id`` column unindexed.

``evaluation.llm_calls`` was evaluated as an alternative to
``gate_results`` at the time and found to need more invented judgment
calls: its ``cost_usd`` column had no stated type at all, and its
``agent_id``/``prompt_id`` columns could technically real-FK to
``catalog.agents``/``catalog.prompts`` (both existed already) — a new
kind of decision about whether those tables' documented id formats
actually line up, not resolved in that step. ``gate_results`` had
neither gap at the time, which is why it was built first; both
``llm_calls`` gaps are now resolved (see its own note below).

``metrics`` — column-for-column per §6: ``metric_id`` PK, ``workflow_id``,
``run_id``, ``metric_name``, ``metric_value``, ``unit``,
``source_component``, ``recorded_at``. Every column is ``NOT NULL`` (§6
marks none nullable). ``metric_value`` is ``NUMERIC(20, 6)`` — the
documentation decision this table was previously blocked on, approved
and recorded in data_model.md §6 in a prior documentation-only step (it
diverges from data_model.md §2's general ``NUMERIC(14,6)`` money
convention deliberately: a metric is not always USD-denominated, so it
gets its own, wider precision rather than borrowing the money
convention). Every other column is a plain identifier/label, so
``Text``, except ``recorded_at``.

``recorded_at`` is ``TIMESTAMP(timezone=True)`` with **no server
default** — application-supplied, not database-generated, diverging
from data_model.md §2's general timestamp convention ("database-generated")
the same deliberate way ``workflow_events.occurred_at`` and
``governance.audit_log.occurred_at`` already do: this column answers
"when did the underlying measurement actually happen," a fact the
application knows and the database commit clock does not — the same
reasoning, applied to a third table now, not a fresh one-off invention.

``metrics.workflow_id`` gets the by-now-standard real foreign key to
``workflow_instances``. ``metrics.run_id`` now also gets one, against
``experiment_runs.run_id`` (``0026_metrics_run_id_fk``) — deliberately
deferred when this table was first created (retrofitting it was not
part of that step's approved scope, unlike ``experiment_runs.
experiment_id``'s own retrofit, approved as a distinct, later step at
the time), now closed the same "verify against the full test suite,
don't assume" way every other retrofit in this persistence layer has
been. Unlike every prior retrofit in this file, this one was **not**
safe against the existing test suite unmodified: three tests in
``tests/integration/persistence/test_migrations.py`` inserted a
``metrics`` row referencing ``run_id = 'run_1'``, a value with no
matching ``experiment_runs`` row anywhere in this codebase (nothing
writes to either table in real application code yet — no Evaluation
Engine exists). Two of the three needed a real ``experiment_runs`` row
(and, transitively, a real ``experiments`` row for *its* own foreign
key) seeded before the ``metrics`` insert; the third already expected
failure for an unrelated reason (an unregistered ``workflow_id``) and
needed no change. ``run_id`` was already indexed before this retrofit,
the same "index the natural lookup column even before its foreign key
exists" precedent already used for ``experiment_runs.experiment_id``
before *that* FK was added.

No ``CHECK`` constraint anywhere on this table: §6 gives no column here
a documented closed value list.

Two indexes beyond the primary key, mirroring ``experiment_runs``' own
shape exactly (also two reference-style columns, one real FK, one not
yet): ``workflow_id`` (the standard FK index) and ``run_id`` (the
natural "all metrics for this experiment run" query).

``llm_calls`` — column-for-column per §6: ``call_id`` PK, ``workflow_id``,
``step_id``, ``agent_id``, ``prompt_id``, ``prompt_version``,
``model_alias``, ``provider``, ``model_id``, ``input_tokens``,
``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens``,
``cost_usd``, ``latency_ms``, ``stop_reason``, ``retries``,
``fallback_used``, ``degradations`` (jsonb). Every column is ``NOT NULL``
(§6 marks none nullable, and unlike ``catalog.packs``' lifecycle
columns, nothing here is conditionally "hasn't happened yet" — a
completed LLM call has a real value for every one of these by the time
a row would ever be written).

``cost_usd`` is ``NUMERIC(18, 6)`` — the documentation decision this
table was blocked on, approved and recorded in data_model.md §6
alongside ``metrics.metric_value``'s own precision decision in the same
prior documentation-only step; it diverges from data_model.md §2's
general ``NUMERIC(14,6)`` money convention deliberately, the identical
reasoning already applied to ``metrics.metric_value``. ``input_tokens``,
``output_tokens``, ``cache_read_tokens``, and ``cache_write_tokens`` are
``BigInteger`` — mirroring ``workflow_instances.total_tokens`` exactly,
the only existing precedent in this persistence layer for a
token-count column, applied here to four per-call counts instead of one
running total. ``latency_ms`` is ``Integer``, the identical type and
reasoning already used for ``gate_results.duration_ms`` (an unambiguous
millisecond count). ``retries`` is ``Integer`` (a count, the same
reasoning as ``experiment_runs.replicate_index``/``experiments.
runs_per_variant``). ``fallback_used`` is ``Boolean``, mirroring
``experiment_runs.served_from_cache`` (a plain yes/no fact). Every
other column is a plain identifier/label, so ``Text``, except
``degradations``, which is ``JSONB`` — explicitly marked so in §6
itself.

**``agent_id`` gets a real foreign key** — to
:data:`ai_os_kernel.persistence.catalog_schema.agents.c.agent_id` — the
documentation decision that previously blocked this table, now
resolved: ``catalog.agents`` already exists and uses exactly the id
shape this column stores. This is the same persistence-to-persistence,
real-``Column``-object pattern already established for ``workflow_id``
→ ``persistence.schema.workflow_instances`` (never a string-based
cross-``MetaData`` reference, which does not resolve — see
:mod:`ai_os_kernel.persistence.cross_schema_foreign_keys` for why), just
against a different sibling module (`catalog_schema.py`, which — like
`schema.py` — does not import `evaluation_schema.py` back, so importing
`catalog_schema.py`'s tables here is one-directional and never a
circular import). ``step_id`` gets no foreign key, the identical reason
``workflow_events.step_id``/``approvals.step_id``/``gate_results.
step_id`` carry none.

**``prompt_id``/``prompt_version`` get a composite foreign key** against
``catalog.prompts``' own composite primary key, ``(prompt_id,
version)`` — retrofitted in migration ``0024_catalog_prompts_pk``, the
same migration that gave ``catalog.prompts`` that composite key.
Originally a single-column foreign key against ``prompts.c.prompt_id``
alone (created with this table); that stopped being possible the moment
``catalog.prompts`` lost its own single-column unique constraint on
``prompt_id`` (Postgres requires a foreign key's referenced columns to
carry a unique constraint or primary key of the exact same shape,
resolved as a composite pair the same way :data:`ai_os_kernel.
persistence.schema.workflow_instances`'s own ``definition_id``/
``definition_version`` composite foreign key already resolves against
``catalog.workflow_definitions``). This also closes a latent
correctness gap the single-column version had: before the retrofit,
``prompt_version`` was never checked against ``catalog.prompts`` at
all, so a row could reference a real ``prompt_id`` together with a
``prompt_version`` that did not match any actual row for it.

No ``CHECK`` constraint on ``stop_reason``: §6 gives it no documented
value list, the same open-ended reasoning already applied throughout
(e.g. `stop_reason` values an LLM provider might return — `end_turn`,
`max_tokens`, `tool_use`, ... — are illustrative, not a closed set
data_model.md actually enumerates).

Three indexes beyond the primary key: ``workflow_id``, ``agent_id``, and
``prompt_id`` — every real foreign key column in this table gets one,
the same convention already applied to every other real FK in this
persistence layer (``run_manifests.workflow_id``, ``experiment_runs.
workflow_id``/``experiment_id``, ``gate_results.workflow_id``,
``metrics.workflow_id``). ``step_id`` is not indexed, following the
same precedent that already leaves every other table's own ``step_id``
column unindexed.

This module does not touch ``persistence/schema.py``,
``cross_schema_foreign_keys.py``, or any ``workflow``-schema migration.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ai_os_kernel.persistence.catalog_schema import agents, prompts, workflow_definitions
from ai_os_kernel.persistence.schema import workflow_instances

metadata = sa.MetaData(schema="evaluation")

run_manifests = sa.Table(
    "run_manifests",
    metadata,
    sa.Column("run_manifest_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("manifest", JSONB, nullable=False),
    sa.Column("manifest_hash", sa.Text, nullable=False),
)

sa.Index("ix_run_manifests_workflow_id", run_manifests.c.workflow_id)

experiment_runs = sa.Table(
    "experiment_runs",
    metadata,
    sa.Column("run_id", sa.Text, primary_key=True),
    sa.Column("experiment_id", sa.Text, nullable=False),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("variant_key", sa.Text, nullable=False),
    sa.Column("model_alias", sa.Text, nullable=False),
    sa.Column("resolved_model_id", sa.Text, nullable=False),
    sa.Column("replicate_index", sa.Integer, nullable=False),
    sa.Column("served_from_cache", sa.Boolean, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
)

sa.Index("ix_experiment_runs_workflow_id", experiment_runs.c.workflow_id)
sa.Index("ix_experiment_runs_experiment_id", experiment_runs.c.experiment_id)

experiments = sa.Table(
    "experiments",
    metadata,
    sa.Column("experiment_id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("definition_id", sa.Text, nullable=False),
    sa.Column("definition_version", sa.Text, nullable=False),
    sa.Column("variables", JSONB, nullable=False),
    sa.Column("pinned_conditions", JSONB, nullable=False),
    sa.Column("runs_per_variant", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["definition_id", "definition_version"],
        [workflow_definitions.c.definition_id, workflow_definitions.c.version],
        name="fk_experiments_definition_id_version",
    ),
)

sa.Index("ix_experiments_definition_id", experiments.c.definition_id)
sa.Index("ix_experiments_status", experiments.c.status)

# Retrofit: experiment_runs.experiment_id -> experiments.experiment_id.
# Safe to attach inline here (unlike workflow_instances.run_manifest_id,
# see cross_schema_foreign_keys.py) because both tables share this one
# module and MetaData — no circular import is possible.
experiment_runs.append_constraint(
    sa.ForeignKeyConstraint(
        ["experiment_id"],
        [experiments.c.experiment_id],
        name="fk_experiment_runs_experiment_id",
    )
)

gate_results = sa.Table(
    "gate_results",
    metadata,
    sa.Column("result_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("step_id", sa.Text, nullable=False),
    sa.Column("gate_id", sa.Text, nullable=False),
    sa.Column("gate_version", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("metrics", JSONB, nullable=False),
    sa.Column("messages", JSONB, nullable=False),
    sa.Column("duration_ms", sa.Integer, nullable=False),
    # `0038_gate_results_created_at`. Server-defaulted rather than
    # caller-supplied: the database's own clock is the one honest source
    # for "when did this gate resolve", and no writer should be able to
    # backdate a trend point. Mirrors `llm_calls.created_at`, added for
    # the identical reason by `0035`.
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
)

sa.Index("ix_gate_results_workflow_id", gate_results.c.workflow_id)
sa.Index("ix_gate_results_created_at", gate_results.c.created_at)
sa.Index("ix_gate_results_status", gate_results.c.status)

metrics = sa.Table(
    "metrics",
    metadata,
    sa.Column("metric_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column(
        "run_id",
        sa.Text,
        sa.ForeignKey(experiment_runs.c.run_id),
        nullable=False,
    ),
    sa.Column("metric_name", sa.Text, nullable=False),
    sa.Column("metric_value", sa.Numeric(20, 6), nullable=False),
    sa.Column("unit", sa.Text, nullable=False),
    sa.Column("source_component", sa.Text, nullable=False),
    sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_metrics_workflow_id", metrics.c.workflow_id)
sa.Index("ix_metrics_run_id", metrics.c.run_id)

llm_calls = sa.Table(
    "llm_calls",
    metadata,
    sa.Column("call_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("step_id", sa.Text, nullable=False),
    sa.Column(
        "agent_id",
        sa.Text,
        sa.ForeignKey(agents.c.agent_id),
        nullable=False,
    ),
    sa.Column("prompt_id", sa.Text, nullable=False),
    sa.Column("prompt_version", sa.Text, nullable=False),
    sa.Column("model_alias", sa.Text, nullable=False),
    sa.Column("provider", sa.Text, nullable=False),
    sa.Column("model_id", sa.Text, nullable=False),
    sa.Column("input_tokens", sa.BigInteger, nullable=False),
    sa.Column("output_tokens", sa.BigInteger, nullable=False),
    sa.Column("cache_read_tokens", sa.BigInteger, nullable=False),
    sa.Column("cache_write_tokens", sa.BigInteger, nullable=False),
    sa.Column("cost_usd", sa.Numeric(18, 6), nullable=False),
    sa.Column("latency_ms", sa.Integer, nullable=False),
    sa.Column("stop_reason", sa.Text, nullable=False),
    sa.Column("retries", sa.Integer, nullable=False),
    sa.Column("fallback_used", sa.Boolean, nullable=False),
    sa.Column("degradations", JSONB, nullable=False),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.ForeignKeyConstraint(
        ["prompt_id", "prompt_version"],
        [prompts.c.prompt_id, prompts.c.version],
        name="fk_llm_calls_prompt_id_version",
    ),
)

sa.Index("ix_llm_calls_workflow_id", llm_calls.c.workflow_id)
sa.Index("ix_llm_calls_agent_id", llm_calls.c.agent_id)
sa.Index("ix_llm_calls_prompt_id", llm_calls.c.prompt_id)
sa.Index("ix_llm_calls_created_at", llm_calls.c.created_at)
