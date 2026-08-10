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
  field of its own (only ``agents``/``requiredTools`` component
  *references*, not a permissions list) — the real, documented source
  is the *manifest's* own ``workflows[].permissions``, which this class
  has no access to at this call site (only a bare ``pack_id`` string,
  never the manifest itself). :meth:`register` therefore still writes
  an empty JSONB array here, exactly as before — genuinely correct only
  when nothing has registered this ``(definition_id, version)`` for
  real yet; see this module's own docstring for why that is safe (the
  manifest-driven writer runs first, in every real pack-installation
  path, and this upsert's own ``ON CONFLICT DO NOTHING`` never
  overwrites a row already carrying the real value).
- ``validated_at`` — the moment this writer runs, application-supplied
  (no server default), the same reasoning already applied to every
  other "when did this actually happen" column in this persistence
  layer (``workflow_events.occurred_at``, ``governance.audit_log.
  occurred_at``, ``evaluation.metrics.recorded_at``,
  ``catalog.pack_state_transitions.occurred_at``).

**``declared_permissions`` is now genuinely populated by a second writer
(2026-08-03, `P03-S05-M14-T10`) — closing the gap this module's own
column mapping used to disclose ("`WorkflowDefinition` has no
permissions field of its own today ... stored as an empty JSONB array
until a documented field for it exists").** That documented field now
exists, one level up: the *manifest's* own ``workflows[].permissions``
(the "permission ceiling for every agent and tool in this workflow",
``platform_sdk/schemas/manifest.schema.json``) — never a field added to
``WorkflowDefinition`` itself, which stays what it always was, the
definition *file's* own validated contract, with no notion of which
pack or manifest it belongs to.
:func:`~ai_os_kernel.capability_manager.manifest_catalog_installer.
derive_workflow_definition_rows` derives real rows straight from that
manifest field at pack-registration time, using
:func:`build_workflow_definition_row` below (the same row-shape logic
:meth:`SqlWorkflowDefinitionCatalog.register` itself now uses, extracted
so neither writer duplicates the other's column mapping) — writing a
real, non-empty ``declared_permissions`` *before* any instance is ever
created from that workflow, so this class's own ``register`` (called
later, at instance-creation time, with no manifest in scope to source a
permission ceiling from — see :meth:`register`'s own docstring) upserts
against an ``ON CONFLICT DO NOTHING`` that is already correct, real
data, not the placeholder empty list it would write on its own.
:meth:`get_declared_permissions` is the new read half, the seam
:mod:`ai_os_kernel.workflow_engine.service` calls once per real
``advance()`` — see :mod:`ai_os_kernel.workflow_engine.registry`'s own
docstring for how that reaches the resolution check itself.

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

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import workflow_definitions
from ai_os_kernel.workflow_engine.errors import WorkflowDefinitionRegistrationError
from ai_os_kernel.workflow_engine.models import WorkflowDefinition

_GRAPH_EXCLUDED_FIELDS = {"id", "version", "inputs", "outputs"}


def build_workflow_definition_row(
    definition: WorkflowDefinition,
    *,
    pack_id: str,
    declared_permissions: Collection[str],
) -> dict[str, Any]:
    """The one real column mapping from a validated :class:`WorkflowDefinition`
    to a ``catalog.workflow_definitions`` row — shared by
    :meth:`SqlWorkflowDefinitionCatalog.register` (``declared_permissions``
    always ``[]``, no manifest in scope) and
    :func:`~ai_os_kernel.capability_manager.manifest_catalog_installer.
    derive_workflow_definition_rows` (the real, manifest-sourced value),
    so the two writers can never silently drift on what the other five
    columns mean. See this module's own docstring for the full column
    mapping rationale."""
    return {
        "definition_id": definition.id,
        "version": definition.version,
        "pack_id": pack_id,
        "graph": definition.model_dump(mode="json", by_alias=True, exclude=_GRAPH_EXCLUDED_FIELDS),
        "inputs_schema": definition.inputs,
        "outputs_schema": definition.outputs,
        "declared_permissions": list(declared_permissions),
        "validated_at": datetime.now(UTC),
    }


def _row_to_definition(row: sa.RowMapping) -> WorkflowDefinition:
    """The exact inverse of :func:`build_workflow_definition_row`'s own
    ``graph``/``inputs_schema``/``outputs_schema`` split — shared by
    :meth:`SqlWorkflowDefinitionCatalog.get`/:meth:`~SqlWorkflowDefinitionCatalog.
    list_all` so the one real reconstruction is never duplicated."""
    payload: dict[str, Any] = {
        **row["graph"],
        "id": row["definition_id"],
        "version": row["version"],
        "inputs": row["inputs_schema"],
        "outputs": row["outputs_schema"],
    }
    return WorkflowDefinition.model_validate(payload)


class WorkflowDefinitionCatalog(Protocol):
    """Persistence boundary for registering, and now reading back, a
    validated :class:`WorkflowDefinition` in
    ``catalog.workflow_definitions`` — the seam a fake implementation
    substitutes in unit tests (ADR-0004: interface-driven, configuration
    over code)."""

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None: ...

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None: ...

    async def get_declared_permissions(
        self, *, definition_id: str, version: str
    ) -> frozenset[str]: ...

    async def list_all(self) -> list[WorkflowDefinition]: ...


class SqlWorkflowDefinitionCatalog:
    """The only implementation of :class:`WorkflowDefinitionCatalog` at
    this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None:
        row = build_workflow_definition_row(definition, pack_id=pack_id, declared_permissions=[])

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    pg_insert(workflow_definitions)
                    .values(**row)
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
        return _row_to_definition(row)

    async def list_all(self) -> list[WorkflowDefinition]:
        """api_architecture.md §6.1's own documented ``GET
        /api/v1/workflow_definitions`` ("Registered definitions") —
        every real, registered row, reusing :meth:`get`'s own lossless
        reconstruction. Deliberately unpaginated, the same "genuinely
        small, bounded collection" reasoning `list_pending` (Approvals)
        already establishes: a workflow *definition* registers once per
        real, distinct version ever written by a pack, not once per
        real run — a handful of rows in practice, not a growing log."""
        async with self._engine.connect() as connection:
            result = await connection.execute(sa.select(workflow_definitions))
            rows = result.mappings().all()
        return [_row_to_definition(row) for row in rows]

    async def get_declared_permissions(self, *, definition_id: str, version: str) -> frozenset[str]:
        """The workflow term of ADR-0023's monotonic-narrowing chain
        (``P03-S05-M14-T10``): ``catalog.workflow_definitions.
        declared_permissions`` for one real, pinned
        ``(definition_id, version)`` — the same composite key a
        ``WorkflowInstance`` already stores (``instance.definition_id``/
        ``instance.definition_version``), needing no snapshot of its own
        (unlike the principal term) since that pin, unlike a bearer
        token, is never ephemeral: the row it points at is immutable by
        version (this module's own docstring), so a fresh read always
        returns the identical answer a snapshot would have.

        Returns an empty ``frozenset`` both when no row exists for this
        key and when a real row exists but its own ``declared_permissions``
        is ``[]`` — the two are indistinguishable at the storage layer
        today (the column has no separate "not yet derived" marker), and
        this module's own writers only ever populate a real, non-empty
        list when a manifest actually declared one
        (:func:`~ai_os_kernel.capability_manager.
        manifest_catalog_installer.derive_workflow_definition_rows`).
        :mod:`~ai_os_kernel.workflow_engine.registry`'s own caller treats
        an empty result as "unenforced," the identical safe default
        ``principal_permissions=None`` already establishes — never as
        "this workflow may exercise zero permissions," which would
        incorrectly refuse every resolution under a workflow that simply
        predates real derivation (the demo workflow, today).
        """
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_definitions.c.declared_permissions).where(
                    workflow_definitions.c.definition_id == definition_id,
                    workflow_definitions.c.version == version,
                )
            )
            declared_permissions = result.scalar_one_or_none()
        return frozenset(declared_permissions or [])
