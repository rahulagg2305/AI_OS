"""Canonical Core table definitions for catalog persistence.

Mirrors docs/08_database/data_model.md §5, in the same style as
:mod:`ai_os_kernel.persistence.governance_schema`,
:mod:`ai_os_kernel.persistence.platform_schema`, and
:mod:`ai_os_kernel.persistence.trace_schema`: kept in its own module
with its own ``MetaData`` (schema ``catalog``), a genuinely distinct
bounded context from ``workflow``, ``governance``, ``platform``, and
``trace``. Combined into ``target_metadata`` in ``kernel/alembic/env.py``
alongside the other four.

All six tables §5 documents are now defined here: ``workflow_definitions``,
``prompts``, ``tools``, ``agents``, ``packs``, and now
``pack_state_transitions`` — the last one, whose primary key
(``transition_id``) and required foreign key (``pack_id`` → ``packs.
pack_id``) were approved and recorded in data_model.md §5 in the same
step that implements them, exactly as ``packs``' own primary key
decision was recorded before that table was built. This module only
implements approved decisions, it does not make them.

``workflow_definitions`` was added first because it has immediate,
already-flagged value: the module docstring of
:mod:`ai_os_kernel.persistence.schema` deferred a foreign key from
``workflow_instances`` to it since the very first migration, purely
because it did not exist yet. That retrofit was itself blocked further
on an open question: data_model.md §5 originally gave this table a
single ``definition_id`` **PK**, while ``workflow_instances`` stores
``definition_id``/``definition_version`` as two separate columns
implying ``definition_id`` is stable *across* versions — those two
readings were in tension. The versioning ambiguity is now resolved: a
documentation decision (data_model.md §4.1/§5) settled that
``definition_id`` is stable across versions and ``version`` is the
separate, varying part, with **uniqueness on (``definition_id``,
``version``)** — so this table's primary key is now that composite
pair, not ``definition_id`` alone (migration
``0021_catalog_wf_definitions_pk``, implemented in this step).

**The foreign key retrofit is now implemented** (in
:mod:`ai_os_kernel.persistence.schema`, not here — this module is
imported *by* that one, not the reverse). It was attempted once before
and reverted, after verifying it broke 37 of 39
``tests/integration/workflow_engine/`` tests with
``ForeignKeyViolationError``, because nothing in this codebase wrote a
row to ``workflow_definitions`` while ``SqlWorkflowInstanceRepository.
create()`` already wrote ``workflow_instances`` rows with an arbitrary
``definition_id``/``definition_version`` pair unconditionally. It is
safe now: a minimal writer,
:class:`ai_os_kernel.workflow_engine.definition_catalog.
SqlWorkflowDefinitionCatalog`, registers a definition before an
instance referencing it is ever created — see that module and
:mod:`ai_os_kernel.persistence.schema`'s own docstring for the full
history. ``workflow_events`` was checked directly against data_model.md
§4.2 and never had a ``definition_id``/``definition_version`` column at
all — the "workflow_instances/workflow_events" phrasing in earlier
reports referring to this deferred FK was imprecise; only
``workflow_instances`` ever needed it.

Schema and migration only — no writer, for any of the six tables.
Nothing in this codebase creates a pack yet (`ManifestLoader` reads and
validates a manifest file; it does not persist one), so nothing would
populate any of them yet either.

``workflow_definitions`` column-for-column per §5: ``definition_id``,
``version`` — together the composite **PRIMARY KEY**, per the resolved
versioning decision above — ``pack_id``, ``graph`` (jsonb),
``inputs_schema``, ``outputs_schema``, ``declared_permissions``,
``validated_at``. Only ``graph`` is explicitly marked ``(jsonb)`` in
§5's compact row format; ``inputs_schema``, ``outputs_schema``, and
``declared_permissions`` are typed ``JSONB`` here too, by direct analogy
to every other structured/nested field already in this persistence
layer (data_model.md §2's own convention: "Structured payloads | JSONB
with a schema_version column alongside";
:class:`ai_os_kernel.workflow_engine.models.WorkflowDefinition`'s own
``inputs``/``outputs`` are JSON Schema documents held the same way).

**This table's primary key changed from a single-column ``definition_id``
to the composite ``(definition_id, version)`` in a later migration**
(``0021_catalog_wf_definitions_pk``, after ``0008_catalog_wf_definitions``
originally created it single-column) — this Python definition reflects
the table's *current* shape, matching the "live target for future
autogenerate diffing" role this module's introduction already assigns
it; the migration files remain the historical record of each step. The
change is safe by construction, independent of whether any rows exist:
a single-column ``definition_id`` primary key already guarantees
``definition_id`` is unique on its own, and a value that is unique on
one column is trivially still unique on that column *plus* another —
so no existing row could ever violate the new, strictly broader
composite constraint.

``prompts`` column-for-column per §5: ``prompt_id``, ``version`` —
together the composite **PRIMARY KEY**, per the resolved versioning
decision below — ``pack_id``, ``content``, ``input_schema``,
``content_hash`` — "versions are immutable" (§5), the same rule
``workflow_definitions`` documents. ``content`` is typed ``sa.Text``,
not ``JSONB``: `prompt_engine.md` §12 ("Storage Format and Cache
Boundary") states a prompt's content is exactly the raw Markdown
template file, not a structured document. ``input_schema`` *is*
``JSONB`` — the expected-variables JSON Schema, the same "JSON Schema
document → JSONB" reasoning used everywhere else in this persistence
layer. ``content_hash`` is `prompt_engine.md`'s own stated purpose for
this column: "records `content_hash` per version, so what was actually
sent is verifiable after the fact" — a plain text digest, the same role
``governance.audit_log.row_hash`` plays for audit rows.

**This table's primary key changed from a single-column ``prompt_id``
to the composite ``(prompt_id, version)`` in a later migration**
(``0024_catalog_prompts_pk``, after ``0009_catalog_prompts`` originally
created it single-column) — the identical situation
``workflow_definitions`` was already in (see above), discovered while
building a second ``PromptEngine`` implementation
(:class:`ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`) against
this table: a single-column ``prompt_id`` primary key made it
impossible to store two versions of the same prompt as separate rows,
even though "versions are immutable — a change creates a new version
row" (§5) already implied multiple rows must be possible. Safe by
construction for the identical reason the ``workflow_definitions``
migration was: a value unique on ``prompt_id`` alone is trivially still
unique on ``prompt_id`` plus ``version``. This Python definition
reflects the table's *current* shape; the migration files remain the
historical record of each step.

**``evaluation.llm_calls.prompt_id``/``prompt_version`` were
retrofitted from a single-column foreign key (against ``prompt_id``
alone) to a composite foreign key against this table's new
``(prompt_id, version)`` pair, in the same migration.** A single-column
foreign key on `prompt_id` alone stopped being possible the moment this
table's own unique constraint on `prompt_id` alone was replaced by the
composite one — Postgres requires a foreign key's referenced columns to
carry a unique constraint or primary key of the exact same shape. See
:mod:`ai_os_kernel.persistence.evaluation_schema` for the retrofit
itself.

``tools`` column-for-column per §5: ``tool_id`` PK, ``pack_id``,
``version``, ``trust_tier``, ``input_schema``, ``output_schema``,
``required_permissions``. ``trust_tier`` gets a ``CHECK`` constraint —
unlike ``workflow_definitions``/``prompts``, which have no enum-like
column at all — grounded in the exact two values
:class:`ai_os_kernel.workflow_engine.tool.TrustTier` already declares
(``tier1_sandboxed``, ``tier2_trusted``), not a fresh interpretation.
Those two literal strings are duplicated here rather than importing
``TrustTier`` itself, for the same two reasons ``workflow_steps.step_type``'s
``_STEP_TYPES`` tuple already duplicates
:class:`ai_os_kernel.workflow_engine.models.StepType` instead of
importing it in :mod:`ai_os_kernel.persistence.schema`: the
``persistence`` layer does not import from ``workflow_engine`` (that
dependency already runs the other way — ``workflow_engine`` imports
persistence tables, never the reverse), and a migration must stay a
frozen historical record of what its ``CHECK`` constraint enforced *at
that time*, not a live reflection of an enum that could change later.
``input_schema``/``output_schema`` are ``JSONB`` (JSON Schema documents,
matching :class:`ai_os_kernel.workflow_engine.tool.Tool`'s own
``output_schema: dict[str, Any]``); ``required_permissions`` is
``JSONB`` too, the same reasoning already applied to
``workflow_definitions.declared_permissions`` (a list is structured
data, per data_model.md §2's own JSONB convention).

``agents`` column-for-column per §5: ``agent_id`` PK ("fully qualified
``pack_id/agent_slug``" — a formatting note about the string's shape,
not a second column), ``pack_id``, ``version``, ``input_schema``,
``output_schema``, ``required_permissions``, ``required_tools``. Both
schema fields are ``JSONB`` for the identical reason ``tools``' are;
``required_permissions`` and ``required_tools`` are ``JSONB`` too — the
same "a list is structured data" reasoning, and ``required_tools``
mirrors :class:`ai_os_kernel.workflow_engine.models.WorkflowDefinition`'s
own ``required_tools: list[str]`` field exactly. Note that the
in-process :class:`ai_os_kernel.workflow_engine.agent.Agent` Protocol
deliberately has *no* ``input_schema`` (no per-step input-mapping
mechanism exists yet to validate against) — that is a runtime-contract
deferral, unrelated to this catalog table, which documents what a
pack's manifest *declares* about an agent, independent of what today's
trivial in-process invocation path uses.

**``tools``/``agents`` both gained an ``entrypoint`` column in a later
migration** (``0028_catalog_entrypoint``), closing a gap discovered
while building a second, ``catalog``-backed implementation of
:class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry`/
:class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`: the Agent
Contract (agent_architecture.md) and the Tool Contract have always
required an ``entrypoint``, and ``platform_sdk/schemas/manifest.schema.json``'s
own ``agents[]``/``tools[]`` entries already require and validate one
(pattern ``^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$``, "Python
import path, ``module.path:ClassName``") — but this table never had a
column for it. ``entrypoint`` is ``sa.Text``, ``NOT NULL`` (required in
the manifest schema, the same "required in the manifest → ``NOT NULL``
here" pattern every other column on these two tables already follows),
with no ``CHECK`` constraint mirroring the manifest schema's own regex:
format validation for patterned strings is the Manifest Loader's job at
manifest-load time (the same convention already followed for
``agent_id``'s own ``pack_id/agent_slug`` shape and ``tool_id``'s
dot-namespaced one — neither gets a Postgres-level format constraint
either). Schema and migration only: nothing reads this column yet
— :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`/
:class:`~ai_os_kernel.workflow_engine.registry.SqlToolRegistry` still
only confirm a row exists and return the same trivial ``EchoAgent``/
``EchoTool`` stand-in regardless of what ``entrypoint`` says — real
entrypoint loading (dynamic import, construction) is explicitly out of
scope for this step, Capability Manager territory (Stage C).

``packs`` column-for-column per §5, per the now-resolved primary-key
decision: ``pack_id`` **PK**, ``version``, ``state`` (the eight-value
canonical lifecycle §5 itself lists and `capability_manager.md` §4
defines as *the* single authority for it — the identical "canonical list is documented,
so enforce it" reasoning already applied to
``workflow_instances.status``/``approvals.status``/``tools.trust_tier``,
so ``state`` gets a ``CHECK`` constraint), ``manifest`` (jsonb),
``sdk_version``, ``min_kernel_version``, ``installed_at``,
``activated_at``, ``health`` (jsonb).

``packs`` is the one table in this module where §5's nullability gap is
**not** resolved as "every column `NOT NULL`" — capability_manager.md §4
documents ``discovered`` as the *first* lifecycle state a pack row can
be in, before ``installed`` or ``activated`` are ever reached, so a
freshly-discovered pack's row cannot yet have a real ``installed_at`` or
``activated_at`` value. Both are nullable, by the identical reasoning
already used for ``workflow_instances.completed_at`` (also
timestamp-typed, also "hasn't happened yet," also not explicitly marked
``NULL`` in its own compact data_model.md row). ``health`` is nullable
too, for the same "hasn't happened yet" class of reason
``workflow_instances.error``/``outputs`` are nullable — capability_manager.md
§3 scopes health *monitoring* to "activated packs," so there is nothing
to hold before then. ``version``, ``state``, ``manifest``,
``sdk_version``, and ``min_kernel_version`` are all ``NOT NULL``: every
one is required manifest content, present from the moment a pack is
first discovered and this row is first written.

``pack_state_transitions`` column-for-column per §5's now-resolved
shape: ``transition_id`` **PK**, ``pack_id`` (required foreign key to
``packs.pack_id`` — the approved decision this step implements),
``from_state``, ``to_state``, ``reason``, ``actor``, ``occurred_at``.
Every column is ``NOT NULL`` (§5 marks none nullable — including
``from_state``: whether the very first-ever transition into
``discovered`` should log a real ``from_state`` or something else is a
question for whoever eventually builds the writer, not invented here by
leaving the column nullable on spec). ``from_state``/``to_state`` get a
``CHECK`` constraint against the identical eight-value ``_PACK_STATES``
tuple already defined above for ``packs.state`` — not a new list, the
same "canonical list is documented, so enforce it" reasoning applied to
the same domain (a pack transition is necessarily *from* one pack
lifecycle state *to* another; there is no third vocabulary for these two
columns to draw from). Reused directly (``_PACK_STATES``), not
duplicated, since both tables already share one module. ``occurred_at``
has no server default — application-supplied, the same deliberate
divergence from the general "database-generated" timestamp convention
already used for ``workflow_events.occurred_at``, ``governance.
audit_log.occurred_at``, and ``evaluation.metrics.recorded_at``: it
answers "when did this transition actually happen," a fact the
application knows and the database commit clock does not.

**`pack_state_transitions.pack_id` gets a real foreign key to
`packs.pack_id`** — the one FK this step's approved decision explicitly
requires. Same-module, same-`MetaData` retrofit pattern already used for
`experiment_runs.experiment_id` → `experiments.experiment_id`: trivial,
no import-ordering hazard, since both tables already live here. This
does **not** retrofit `workflow_definitions`/`prompts`/`tools`/`agents`'
own `pack_id` columns into foreign keys against `packs.pack_id` — those
remain out of scope, unchanged from the `packs` step.

Every other column, across all six tables, is ``NOT NULL`` (§5 marks
none of them nullable), including ``workflow_definitions.validated_at``:
data_model.md §5 also states "Prompt and workflow-definition versions
are immutable: a change creates a new version row," which reads as "a
row is written once a version exists as a validated artifact," not
written first and validated later.

**No foreign key on `packs.pack_id` from `workflow_definitions`/
`prompts`/`tools`/`agents`.** Those four tables' own `pack_id` columns
remain un-FK'd — out of scope for every step so far, a distinct, later
step.

Indexes beyond primary keys: `state` on `packs` (the "all packs in a
given lifecycle state" query, the same reasoning already applied to
`workflow_instances.status`/`approvals.status`/`experiments.status`/
`gate_results.status`); `pack_id` on `pack_state_transitions` (the
standard real-FK index, the same convention every real FK in this
persistence layer already gets) and `occurred_at` on
`pack_state_transitions` (the natural "this pack's history, in order"
query, mirroring `governance.audit_log.occurred_at`/`governance.
config_changes.changed_at`'s own recency indexes). `version` is not
indexed anywhere in this module: no table here indexes a bare `version`
column.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(schema="catalog")

workflow_definitions = sa.Table(
    "workflow_definitions",
    metadata,
    sa.Column("definition_id", sa.Text, primary_key=True),
    sa.Column("version", sa.Text, primary_key=True),
    sa.Column("pack_id", sa.Text, nullable=False),
    sa.Column("graph", JSONB, nullable=False),
    sa.Column("inputs_schema", JSONB, nullable=False),
    sa.Column("outputs_schema", JSONB, nullable=False),
    sa.Column("declared_permissions", JSONB, nullable=False),
    sa.Column("validated_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

sa.Index("ix_workflow_definitions_pack_id", workflow_definitions.c.pack_id)

prompts = sa.Table(
    "prompts",
    metadata,
    sa.Column("prompt_id", sa.Text, primary_key=True),
    sa.Column("version", sa.Text, primary_key=True),
    sa.Column("pack_id", sa.Text, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("input_schema", JSONB, nullable=False),
    sa.Column("content_hash", sa.Text, nullable=False),
)

sa.Index("ix_prompts_pack_id", prompts.c.pack_id)

# The exact two values ai_os_kernel.workflow_engine.tool.TrustTier
# declares, duplicated rather than imported — see the module docstring
# for why the persistence layer never imports from workflow_engine.
_TOOL_TRUST_TIERS = (
    "tier1_sandboxed",
    "tier2_trusted",
)

tools = sa.Table(
    "tools",
    metadata,
    sa.Column("tool_id", sa.Text, primary_key=True),
    sa.Column("pack_id", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("entrypoint", sa.Text, nullable=False),
    sa.Column("trust_tier", sa.Text, nullable=False),
    sa.Column("input_schema", JSONB, nullable=False),
    sa.Column("output_schema", JSONB, nullable=False),
    sa.Column("required_permissions", JSONB, nullable=False),
    sa.CheckConstraint(
        "trust_tier IN (" + ", ".join(f"'{t}'" for t in _TOOL_TRUST_TIERS) + ")",
        name="ck_tools_trust_tier",
    ),
)

sa.Index("ix_tools_pack_id", tools.c.pack_id)

agents = sa.Table(
    "agents",
    metadata,
    sa.Column("agent_id", sa.Text, primary_key=True),
    sa.Column("pack_id", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("entrypoint", sa.Text, nullable=False),
    sa.Column("input_schema", JSONB, nullable=False),
    sa.Column("output_schema", JSONB, nullable=False),
    sa.Column("required_permissions", JSONB, nullable=False),
    sa.Column("required_tools", JSONB, nullable=False),
)

sa.Index("ix_agents_pack_id", agents.c.pack_id)

# The eight-value canonical lifecycle capability_manager.md §4 defines as
# the single authority for it (data_model.md §5 lists the identical set).
# No existing Python enum to mirror yet — capability_manager itself is
# still an empty, not-yet-built Kernel component — so these are sourced
# directly from the two architecture documents, the same way
# _INSTANCE_STATUSES/_APPROVAL_STATUSES were in persistence/schema.py
# before any corresponding enum existed either.
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

packs = sa.Table(
    "packs",
    metadata,
    sa.Column("pack_id", sa.Text, primary_key=True),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("manifest", JSONB, nullable=False),
    sa.Column("sdk_version", sa.Text, nullable=False),
    sa.Column("min_kernel_version", sa.Text, nullable=False),
    sa.Column("installed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("health", JSONB, nullable=True),
    sa.CheckConstraint(
        "state IN (" + ", ".join(f"'{s}'" for s in _PACK_STATES) + ")",
        name="ck_packs_state",
    ),
)

sa.Index("ix_packs_state", packs.c.state)

pack_state_transitions = sa.Table(
    "pack_state_transitions",
    metadata,
    sa.Column("transition_id", sa.Text, primary_key=True),
    sa.Column(
        "pack_id",
        sa.Text,
        sa.ForeignKey(packs.c.pack_id),
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
)

sa.Index("ix_pack_state_transitions_pack_id", pack_state_transitions.c.pack_id)
sa.Index(
    "ix_pack_state_transitions_occurred_at_desc",
    pack_state_transitions.c.occurred_at.desc(),
)
