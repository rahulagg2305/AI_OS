"""Canonical Core table definitions for workflow-state persistence.

Mirrors docs/08_database/data_model.md §4.1, §4.2, §4.4 exactly. This
module is the live target for Alembic's ``target_metadata`` (used for
future autogenerate diffing); the migration in
``kernel/alembic/versions/`` is the authority for what has actually been
applied to any given database (data_model.md §14).

Five tables are defined here: ``workflow_instances``, ``workflow_events``,
``workflow_leases``, ``workflow_steps``, and ``approvals`` — every table
data_model.md §4 documents for the ``workflow`` schema. Note that
``approvals`` (data_model.md §4.5) is genuinely named ``approvals``, not
``workflow_approvals``: unlike every other table here, the doc's own
table header (``workflow.approvals``) does not repeat the schema name
inside the table name, and that asymmetry is followed literally rather
than "fixed."

``workflow_steps.status`` deliberately has no ``CHECK`` constraint,
unlike ``workflow_instances.status``: data_model.md §4.1 gives
``workflow_instances.status`` an explicit "canonical state list";
§4.3 gives ``workflow_steps`` no equivalent list for ``status``, so
enumerating one here would be inventing business logic beyond what
was approved. ``workflow_steps.step_type`` does get a ``CHECK``
constraint, because its seven values are already documented
(workflow_architecture.md's Supported Step Types,
:class:`ai_os_kernel.workflow_engine.models.StepType`).

``workflow_steps.prompt_id``/``prompt_version``/``model_alias``
(migration ``0027_workflow_steps_prompt``) complete the mirror of
workflow_architecture.md's Step Contract that ``agent_id``/``tool_id``
started: all five fields a step may declare, recorded on the row for
the step that actually executed. Typed ``sa.Text``, matching
``evaluation.llm_calls``' own ``prompt_id``/``prompt_version``/
``model_alias`` columns exactly (data_model.md §6) — the closest
existing precedent for this shape. Nullable, unlike ``llm_calls``'
versions of the same columns: every step may omit them (only `agent`
steps use them at all, and even there they are optional per the Step
Contract), where `llm_calls` records one completed call that always
has them. **Deliberately no foreign key** on `prompt_id`/`prompt_version`
to `catalog.prompts (prompt_id, version)`, unlike `llm_calls`' own
composite foreign key to the same target: that FK is safe on
`llm_calls` because a real call actually happened against an
already-rendered prompt; here, `prompt_id`/`prompt_version` merely
record what a step *declared*, and no writer exists for
`catalog.prompts` in this codebase (only a reader,
:class:`ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`) — the
identical "no writer, so no real FK yet" reasoning already applied to
this same table's `agent_id`/`tool_id` (no writer for
`catalog.agents`/`catalog.tools` either). No new index, for the same
reason `agent_id`/`tool_id` have none: only `workflow_id` is indexed on
this table.

``approvals.status`` *does* get a ``CHECK`` constraint: §4.5 gives it
an explicit six-value list (``pending``/``approved``/``rejected``/
``changes_requested``/``timed_out``/``cancelled``), the same
"canonical list is documented, so enforce it" reasoning already
applied to ``workflow_instances.status``. Unlike every other table
here, ``approvals`` has no writer yet — this step is schema and
migration only, deliberately: no Human Approval Point execution path
exists yet to populate it (agent/tool/LLM work, out of scope here).

§4.5 lists ``approvals``' columns without marking nullability, the same
gap §4.3 left for ``workflow_steps``. The choices made here follow the
same reasoning already established for the Human Approval Point
Contract (``ai_os_kernel.workflow_engine.models.HumanApprovalPoint``):
``title``/``description``/``options`` are ``NOT NULL`` because that
contract already requires ``name``/``description``/at-least-one
``options`` entry; ``expires_at`` is nullable because the contract's
own ``timeout`` field is optional; ``decided_by``/``decision_comment``/
``decided_at`` are nullable because a ``pending`` approval has not been
decided yet. ``step_id`` is ``NOT NULL`` (a Human Approval Point is
inherently step-scoped) but, like ``workflow_events.step_id``, carries
no foreign key — nothing persists the set of declared step ids a
definition's steps must belong to yet (no ``catalog.workflow_definitions``
table exists).

One documented detail is intentionally deferred, not silently dropped:
``workflow_events`` is described as revoking ``UPDATE``/``DELETE`` for
"the application role" — no such role exists yet (no database-role or
authentication work has landed). Enforced once that role is created.

Two foreign keys remain omitted:

- ``experiment_id`` → ``evaluation.experiments``: omitted because
  attaching it here would need the same kind of circular-import
  workaround ``run_manifest_id`` already needed (below) — not attempted,
  out of scope for every step so far.
- ``run_manifest_id``'s foreign key to ``evaluation.run_manifests`` is
  **not** declared inline in this ``sa.Table(...)`` call below, even
  though that table exists. Doing so would require importing
  ``evaluation_schema.py`` here, which itself imports ``workflow_instances``
  from this module for its own foreign key — a genuine circular import.
  See :mod:`ai_os_kernel.persistence.cross_schema_foreign_keys`, which
  attaches this one constraint from outside both modules instead.

**``definition_id``/``definition_version`` → ``catalog.workflow_definitions``
(``definition_id``, ``version``) is now implemented — a genuine composite
foreign key, attached inline below via a direct import of
:mod:`ai_os_kernel.persistence.catalog_schema`.** This is safe, unlike
``run_manifest_id``, because ``catalog_schema.py`` does not import
anything from this module back, so there is no cycle regardless of
which module a caller happens to import first.

This retrofit was attempted once before and **reverted**: adding the
constraint without a writer for ``catalog.workflow_definitions`` broke
37 of 39 ``tests/integration/workflow_engine/`` tests, because
``SqlWorkflowInstanceRepository.create()`` wrote ``workflow_instances``
rows unconditionally, with no matching catalog row ever able to exist.
It is safe now because
:class:`ai_os_kernel.workflow_engine.service.WorkflowInstanceService.
create_instance` registers the definition via
:class:`ai_os_kernel.workflow_engine.definition_catalog.
WorkflowDefinitionCatalog` — an idempotent upsert — immediately before
creating the instance that references it, on every call, not
conditionally. See that module's docstring for the registration
details and :mod:`ai_os_kernel.workflow_engine.errors`'
``WorkflowDefinitionRegistrationError``/``WorkflowInstanceCreationError``
for how a registration or FK failure surfaces — never a bare
constraint-violation stack trace.

Historical note, corrected during the investigation that led here:
earlier reports and :mod:`ai_os_kernel.persistence.catalog_schema`'s own
docstring described this as a "``workflow_instances``/``workflow_events``"
foreign key. Checked directly against data_model.md §4.2: ``workflow_events``
never had a ``definition_id``/``definition_version`` column at all. Only
``workflow_instances`` ever needed this foreign key.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ai_os_kernel.persistence.catalog_schema import workflow_definitions

metadata = sa.MetaData(schema="workflow")

_INSTANCE_STATUSES = (
    "created",
    "running",
    "waiting_for_human",
    "waiting_for_retry",
    "quality_gate_failed",
    "compensating",
    "completed",
    "failed",
    "cancelled",
)

workflow_instances = sa.Table(
    "workflow_instances",
    metadata,
    sa.Column("workflow_id", sa.Text, primary_key=True),
    sa.Column("definition_id", sa.Text, nullable=False),
    sa.Column("definition_version", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("current_step_id", sa.Text, nullable=True),
    sa.Column("inputs", JSONB, nullable=False),
    sa.Column("outputs", JSONB, nullable=True),
    sa.Column("experiment_id", sa.Text, nullable=True),
    # FK to evaluation.run_manifests attached externally — see
    # ai_os_kernel.persistence.cross_schema_foreign_keys (circular-import
    # avoidance, explained in this module's own docstring above).
    sa.Column("run_manifest_id", sa.Text, nullable=True),
    sa.Column("principal_id", sa.Text, nullable=False),
    # The triggering principal's real, computed SecurityContext.permissions
    # (security_manager.narrowing's principal term), captured once at
    # trigger time — nullable, NULL meaning "not enforced" (a caller
    # with no live SecurityContext, e.g. every real caller before
    # P03-S05-M14-T09), never an empty set, which would incorrectly
    # mean "this principal holds no permissions at all." See
    # ai_os_kernel.workflow_engine.registry's own docstring for why a
    # snapshot, not a live object, is what resolution reads back.
    sa.Column("principal_permissions", JSONB, nullable=True),
    # The Scheduler's own data (workflow_engine.md §5.13, "Scheduler ...
    # delayed/scheduled workflow starts") — NULL means "no scheduled
    # start requested" (every real caller before P02-S01-M05-T13, and
    # every create() call that still omits the new keyword), never "due
    # immediately," which would be indistinguishable from a genuine,
    # very-soon-due schedule. WorkflowScheduler is the one real reader.
    sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("last_event_seq", sa.BigInteger, nullable=False),
    sa.Column("error", JSONB, nullable=True),
    sa.Column("total_cost_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
    sa.Column("total_tokens", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN (" + ", ".join(f"'{s}'" for s in _INSTANCE_STATUSES) + ")",
        name="ck_workflow_instances_status",
    ),
    sa.ForeignKeyConstraint(
        ["definition_id", "definition_version"],
        [workflow_definitions.c.definition_id, workflow_definitions.c.version],
        name="fk_workflow_instances_definition_id_version",
    ),
)

sa.Index("ix_workflow_instances_status", workflow_instances.c.status)
sa.Index("ix_workflow_instances_definition_id", workflow_instances.c.definition_id)
sa.Index("ix_workflow_instances_experiment_id", workflow_instances.c.experiment_id)
sa.Index("ix_workflow_instances_created_at_desc", workflow_instances.c.created_at.desc())

workflow_events = sa.Table(
    "workflow_events",
    metadata,
    sa.Column("event_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("seq", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("schema_version", sa.Integer, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("trace_id", sa.Text, nullable=True),
    sa.Column("step_id", sa.Text, nullable=True),
    sa.Column("agent_id", sa.Text, nullable=True),
    sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.UniqueConstraint("workflow_id", "seq", name="uq_workflow_events_workflow_id_seq"),
)

sa.Index("ix_workflow_events_event_type", workflow_events.c.event_type)
sa.Index("ix_workflow_events_occurred_at_desc", workflow_events.c.occurred_at.desc())
sa.Index("ix_workflow_events_trace_id", workflow_events.c.trace_id)

workflow_leases = sa.Table(
    "workflow_leases",
    metadata,
    sa.Column("lease_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
        unique=True,
    ),
    sa.Column("worker_id", sa.Text, nullable=False),
    sa.Column("acquired_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

_STEP_TYPES = (
    "agent",
    "tool",
    "decision",
    "parallel",
    "sub_workflow",
    "quality_gate",
    "human_approval",
    "foreach",
)

workflow_steps = sa.Table(
    "workflow_steps",
    metadata,
    sa.Column("step_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("step_name", sa.Text, nullable=False),
    sa.Column("step_type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("agent_id", sa.Text, nullable=True),
    sa.Column("tool_id", sa.Text, nullable=True),
    sa.Column("prompt_id", sa.Text, nullable=True),
    sa.Column("prompt_version", sa.Text, nullable=True),
    sa.Column("model_alias", sa.Text, nullable=True),
    sa.Column("inputs", JSONB, nullable=False),
    sa.Column("outputs", JSONB, nullable=True),
    sa.Column("error", JSONB, nullable=True),
    sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("usage", JSONB, nullable=False),
    sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint(
        "step_type IN (" + ", ".join(f"'{t}'" for t in _STEP_TYPES) + ")",
        name="ck_workflow_steps_step_type",
    ),
    sa.UniqueConstraint(
        "workflow_id",
        "step_name",
        "attempt",
        name="uq_workflow_steps_workflow_id_step_name_attempt",
    ),
)

sa.Index("ix_workflow_steps_workflow_id", workflow_steps.c.workflow_id)

_APPROVAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "changes_requested",
    "timed_out",
    "cancelled",
)

approvals = sa.Table(
    "approvals",
    metadata,
    sa.Column("approval_id", sa.Text, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
        nullable=False,
    ),
    sa.Column("step_id", sa.Text, nullable=False),
    sa.Column("approval_class", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("context_digest", sa.Text, nullable=False),
    sa.Column("options", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("decided_by", sa.Text, nullable=True),
    sa.Column("decision_comment", sa.Text, nullable=True),
    sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN (" + ", ".join(f"'{s}'" for s in _APPROVAL_STATUSES) + ")",
        name="ck_approvals_status",
    ),
)

sa.Index("ix_approvals_workflow_id", approvals.c.workflow_id)
sa.Index("ix_approvals_status", approvals.c.status)
