"""Minimal write path for ``catalog.workflow_definitions``.

This is deliberately **not** a Capability Manager or a Manifest Loader
extension — both remain out of scope. It is the smallest seam that lets
:class:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService`
register the :class:`~ai_os_kernel.workflow_engine.models.WorkflowDefinition`
it already holds before creating an instance that references it, which
is what makes ``workflow_instances``' composite foreign key to this
table (data_model.md §4.1, ``persistence/schema.py``) safe to enforce —
see that module's docstring for the full history of why the foreign key
was previously reverted.

Registration is an **upsert keyed on ``(definition_id, version)``**, not
a plain insert: the same definition (already validated once) is
re-registered every time an instance is created from it, since nothing
in this codebase yet performs a separate, one-time registration step
(the Manifest Loader/Capability Manager work that would own that is out
of scope here). ``ON CONFLICT (definition_id, version) DO NOTHING``
rather than ``DO UPDATE``: data_model.md §5 states "workflow-definition
versions are immutable — a change creates a new version row," so a
second registration attempt for a version already on record is treated
as a no-op, not a silent overwrite. If two calls ever disagreed about
what a given version's content should be, that would be an application
bug (the version should have changed), not something this writer papers
over.

Column mapping from :class:`WorkflowDefinition` to the five columns this
writer supplies (``definition_id``/``version`` are the two already
covered by the primary key):

- ``pack_id`` — **not** a field on ``WorkflowDefinition`` (a workflow
  definition file has no notion of which pack it belongs to; that is
  manifest-level knowledge). Supplied explicitly by the caller.
- ``inputs_schema``/``outputs_schema`` — ``definition.inputs``/
  ``definition.outputs`` directly; both are already validated JSON
  Schema documents.
- ``graph`` — the remainder of the validated definition once its
  identity (``id``, ``version``) and I/O contracts (``inputs``,
  ``outputs``, already their own columns) are excluded: ``name``,
  ``description``, ``trigger``, ``steps``, ``agents``,
  ``requiredTools``, ``qualityGates``, ``humanApprovalPoints``,
  ``failureHandling``, ``timeout``, ``retryPolicy``. Data_model.md §5
  gives ``graph`` no further shape than "(jsonb)"; excluding only what
  already has its own column is the least-invented reading that keeps
  the durable catalog record complete — nothing validated is silently
  dropped, which matters for the reproducibility this table exists for
  (ADR-0022).
- ``declared_permissions`` — ``WorkflowDefinition`` has no permissions
  field of its own today (only ``agents``/``requiredTools`` component
  *references*, not a permissions list); stored as an empty JSONB array
  until a documented field for it exists, not silently guessed from the
  component references.
- ``validated_at`` — the moment this writer runs, application-supplied
  (no server default), the same reasoning already applied to every
  other "when did this actually happen" column in this persistence
  layer (``workflow_events.occurred_at``, ``governance.audit_log.
  occurred_at``, ``evaluation.metrics.recorded_at``,
  ``catalog.pack_state_transitions.occurred_at``).

**A real reader now exists (2026-08-02, `P02-S01-M05-T14`) — closing
the "no reader" gap this module's own docstring stated above.**
Investigation (this same step) found the write-only catalog is a
genuine blocker for exactly two of the four capabilities the product
owner asked to unblock — `sub_workflow` (needs to resolve an
*arbitrary* referenced definition by id) and the multi-instance worker
loop (needs to resolve *whichever* definition a discovered, already-
running instance happens to belong to, unknown in advance) — both of
which previously had no real option but a composition-level,
caller-supplied mapping (`P02-S01-M05-T11`/`T12`). `decision`/
`parallel` are a genuinely different, smaller gap: they need no
cross-definition lookup at all (both operate entirely within one
definition's own declared steps) — they stay unwired because no real
running pipeline has yet declared one, not because of this module.
`get` is a lossless round-trip of exactly what `register` already writes —
`graph` already contains every field of the original, validated
definition except `id`/`version`/`inputs`/`outputs` (each already its
own column), so reconstructing `WorkflowDefinition.model_validate(...)`
from the four columns together recovers the identical object, nothing
approximated or re-derived. This is deliberately **not** a general
catalog/versioning system: no listing, no update, no delete, no
"latest version" resolution — a single, exact-key lookup, the smallest
real thing that turns "write-only" into "genuinely readable by the
callers that already need it." See
:class:`~ai_os_kernel.workflow_engine.worker_loop.WorkflowWorkerLoop`
for the first real consumer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import workflow_definitions
from ai_os_kernel.workflow_engine.errors import WorkflowDefinitionRegistrationError
from ai_os_kernel.workflow_engine.models import WorkflowDefinition

_GRAPH_EXCLUDED_FIELDS = {"id", "version", "inputs", "outputs"}


class WorkflowDefinitionCatalog(Protocol):
    """Persistence boundary for registering, and now reading back, a
    validated :class:`WorkflowDefinition` in
    ``catalog.workflow_definitions`` — the seam a fake implementation
    substitutes in unit tests (ADR-0004: interface-driven, configuration
    over code)."""

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None: ...

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None: ...


class SqlWorkflowDefinitionCatalog:
    """The only implementation of :class:`WorkflowDefinitionCatalog` at
    this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None:
        graph = definition.model_dump(mode="json", by_alias=True, exclude=_GRAPH_EXCLUDED_FIELDS)

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    pg_insert(workflow_definitions)
                    .values(
                        definition_id=definition.id,
                        version=definition.version,
                        pack_id=pack_id,
                        graph=graph,
                        inputs_schema=definition.inputs,
                        outputs_schema=definition.outputs,
                        declared_permissions=[],
                        validated_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing(index_elements=["definition_id", "version"])
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowDefinitionRegistrationError(
                f"failed to register workflow definition "
                f"'{definition.id}@{definition.version}': {exc}"
            ) from exc

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None:
        """A plain, unguarded read — the identical "no leasing/locking
        here" shape :meth:`~ai_os_kernel.workflow_engine.repository.
        SqlWorkflowInstanceRepository.get_instance` already establishes
        for a read that exists to be acted on, not raced over. Rebuilds
        the original, validated definition from exactly the four
        columns `register` wrote it from — see this module's own
        docstring for why that round-trip is lossless."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_definitions).where(
                    workflow_definitions.c.definition_id == definition_id,
                    workflow_definitions.c.version == version,
                )
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        payload: dict[str, Any] = {
            **row["graph"],
            "id": row["definition_id"],
            "version": row["version"],
            "inputs": row["inputs_schema"],
            "outputs": row["outputs_schema"],
        }
        return WorkflowDefinition.model_validate(payload)
