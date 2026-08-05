"""Real write path for ``evaluation.run_manifests`` (`P04-S01-M12-T05`)
— the Evaluation Engine's second real producer, alongside
:mod:`~ai_os_kernel.workflow_engine.gate_result_recorder`. ADR-0022's
own obligation 1 ("configuration reproducibility") names a real,
complete field list; this is the first writer that has ever tried to
satisfy it. `evaluation_engine.md` itself has never had a Metrics
Collector/Aggregator/Comparison Computer/Reporting Interface either —
this writer alone does not close that; it closes the one, narrower
"no run manifest is written" gap, real and disclosed as this ticket's
own scope.

**Placement decision, mirroring `gate_result_recorder.py`'s own
reasoning exactly: composed by `WorkflowInstanceService`, not the
Evaluation Engine package.** ADR-0022's own bundle needs every real
step's own persisted declaration (`agentId`/`toolId`/`promptId`/
`promptVersion`) — genuinely available only *after* a run's real
`workflow_steps` rows exist, and only that service's own `advance()`
already knows the exact moment a run genuinely completes (`next_step
is None`, the same signal `advance_workflow` itself uses to write
`workflow_instances.status = "completed"`). ``kernel/src/ai_os_kernel/
evaluation_engine/`` remains docstring-only — the identical "the
functional gap is closed elsewhere" shape that module's own
Implementation Status already documents for `gate_result_recorder.py`.

**Real, multi-table joins — every value read from an already-real,
already-persisted row; nothing invented or estimated:**

- ``workflowDefinitionId``/``workflowDefinitionVersion`` ← the caller-
  supplied, already-validated :class:`~ai_os_kernel.workflow_engine.
  models.WorkflowDefinition`.
- ``kernelVersion`` ← :data:`ai_os_kernel.__version__` — a real,
  installed-package version, not a literal.
- Per step (one entry per real ``step_name``, the *latest* real
  attempt — retries of the same step re-declare the identical
  agent/tool/prompt configuration, so only the outcome differs, the
  identical "highest attempt wins" selection this module's own sibling
  ``quality_gate.py``/``context_manager.resolvers`` already establish,
  duplicated here in miniature rather than imported for the same
  documented reason those two already give): ``agentId``/``toolId``/
  ``promptId``/``promptVersion``/``modelAlias`` ← the step's own real,
  persisted ``workflow_steps`` columns. ``agentVersion``/``toolVersion``
  ← a real, batched join against ``catalog.agents``/``catalog.tools``
  (``None`` when the id resolves to no real catalog row — e.g. the
  Kernel's own in-memory demo agent, never pack-installed — an honest
  absence, not a lookup failure). ``packId``/``packVersion`` ← the
  resolved agent's or tool's own real ``pack_id``, joined again against
  ``catalog.packs``. ``resolvedProvider``/``resolvedModelId`` ← a real,
  batched join against ``evaluation.llm_calls``.

**Three real, disclosed gaps — omitted fields, never fabricated
placeholders (the identical "no speculative fields" discipline
``configuration_manager.models.PlatformConfig``'s own docstring
already states: "Fields exist only once something reads them"):**

1. **"All model parameters actually sent"** (ADR-0022's own named
   field) has no real source anywhere in this codebase —
   ``evaluation.llm_calls`` records tokens/cost/latency, never the
   request's own sampling parameters. Omitted entirely, not recorded
   as a null placeholder.
2. **``resolvedProvider``/``resolvedModelId`` are honestly ``None`` for
   every real workflow run that exists today** — not merely for
   ``se.delivery_pipeline`` specifically. Investigation found a real,
   separate, pre-existing gap while building this: ``AgentStepExecutor.
   _invocation_inputs`` never sets ``"stepId"`` in the ``inputs`` dict
   it builds, so ``PromptedAgent.execute``'s own ``step_id=inputs.
   get("stepId")`` is always ``None``, and
   :class:`~ai_os_kernel.prompted_completion.PromptedCompletionService.
   complete_from_prompt`'s own call-recording guard (`self._call_recorder
   is not None and workflow_id is not None and step_id is not None`)
   therefore never fires for *any* real agent invocation anywhere —
   ``evaluation.llm_calls`` has zero real rows from any real production
   call path today, demo or pipeline. This writer's own join against it
   is real and correct — it will start returning real data the moment
   that separate, pre-existing gap is closed — not fabricated to appear
   populated now.
3. **Context-pack ids/versions and retrieval index generation/embedding
   model version** (both ADR-0022-named) have no real source either:
   :class:`~ai_os_kernel.context_manager.audit_logger.SqlContextAuditLogger`
   — the one real component that *could* answer this — is not wired
   into any real production composition (`bootstrap.py`/
   `delivery_pipeline.py`); `context.context_assemblies` has zero real
   rows from any real run.
4. **"The resolved configuration set"** (ADR-0022's own named field) is
   real and available (`ConfigurationManager.load()`, the identical
   mechanism `RuntimeConfigResolver` already uses), but threading a
   *third* new collaborator (beyond this recorder itself) through all
   three real composition sites is real, disclosed, separate follow-up
   scope — not attempted here, to keep this step's own diff to the one
   collaborator it was scoped to add.

``workflow_instances.run_manifest_id`` — a real, already-migrated,
nullable column with an externally-attached foreign key to
``evaluation.run_manifests`` (``cross_schema_foreign_keys.py``),
written by no caller until now — is now genuinely set to the new
manifest's own id in the same transaction, closing that column's own
"declared, never written" gap too.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel import __version__
from ai_os_kernel.persistence.catalog_schema import agents, packs, tools
from ai_os_kernel.persistence.evaluation_schema import llm_calls, run_manifests
from ai_os_kernel.persistence.schema import workflow_instances, workflow_steps
from ai_os_kernel.workflow_engine.errors import RunManifestRecordingError
from ai_os_kernel.workflow_engine.ids import new_run_manifest_id


class RunManifestStepEntry(BaseModel):
    """One real step's own contribution to the manifest — see this
    module's own docstring for exactly which fields are real joins and
    which are honestly ``None``."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    agent_id: str | None
    agent_version: str | None
    tool_id: str | None
    tool_version: str | None
    pack_id: str | None
    pack_version: str | None
    prompt_id: str | None
    prompt_version: str | None
    model_alias: str | None
    resolved_provider: str | None
    resolved_model_id: str | None


class RunManifest(BaseModel):
    """The real, persisted ``manifest`` JSONB shape — see this module's
    own docstring for the three fields ADR-0022 names that are
    deliberately absent, not fabricated."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    workflow_definition_id: str
    workflow_definition_version: str
    kernel_version: str
    steps: list[RunManifestStepEntry]


class RunManifestRecorder(Protocol):
    """Persistence boundary for recording one completed run's real
    manifest — the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def record(
        self, *, workflow_id: str, definition_id: str, definition_version: str
    ) -> str: ...


class SqlRunManifestRecorder:
    """The only implementation of :class:`RunManifestRecorder` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(self, *, workflow_id: str, definition_id: str, definition_version: str) -> str:
        try:
            async with self._engine.begin() as connection:
                step_rows = (
                    (
                        await connection.execute(
                            sa.select(workflow_steps).where(
                                workflow_steps.c.workflow_id == workflow_id
                            )
                        )
                    )
                    .mappings()
                    .all()
                )

                latest_by_name: dict[str, sa.RowMapping] = {}
                for row in step_rows:
                    existing = latest_by_name.get(row["step_name"])
                    if existing is None or row["attempt"] > existing["attempt"]:
                        latest_by_name[row["step_name"]] = row

                agent_ids = {row["agent_id"] for row in latest_by_name.values() if row["agent_id"]}
                tool_ids = {row["tool_id"] for row in latest_by_name.values() if row["tool_id"]}

                agent_rows: dict[str, sa.RowMapping] = {}
                if agent_ids:
                    result = await connection.execute(
                        sa.select(agents.c.agent_id, agents.c.version, agents.c.pack_id).where(
                            agents.c.agent_id.in_(agent_ids)
                        )
                    )
                    agent_rows = {row["agent_id"]: row for row in result.mappings().all()}

                tool_rows: dict[str, sa.RowMapping] = {}
                if tool_ids:
                    result = await connection.execute(
                        sa.select(tools.c.tool_id, tools.c.version, tools.c.pack_id).where(
                            tools.c.tool_id.in_(tool_ids)
                        )
                    )
                    tool_rows = {row["tool_id"]: row for row in result.mappings().all()}

                pack_ids = {row["pack_id"] for row in agent_rows.values()} | {
                    row["pack_id"] for row in tool_rows.values()
                }
                pack_versions: dict[str, str] = {}
                if pack_ids:
                    result = await connection.execute(
                        sa.select(packs.c.pack_id, packs.c.version).where(
                            packs.c.pack_id.in_(pack_ids)
                        )
                    )
                    pack_versions = {row["pack_id"]: row["version"] for row in result.mappings()}

                call_rows: dict[str, sa.RowMapping] = {}
                result = await connection.execute(
                    sa.select(
                        llm_calls.c.step_id, llm_calls.c.provider, llm_calls.c.model_id
                    ).where(llm_calls.c.workflow_id == workflow_id)
                )
                for row in result.mappings().all():
                    call_rows[row["step_id"]] = row

                entries: list[RunManifestStepEntry] = []
                for step_name in sorted(
                    latest_by_name, key=lambda name: latest_by_name[name]["started_at"]
                ):
                    row = latest_by_name[step_name]
                    agent_row = agent_rows.get(row["agent_id"]) if row["agent_id"] else None
                    tool_row = tool_rows.get(row["tool_id"]) if row["tool_id"] else None
                    pack_id = (agent_row["pack_id"] if agent_row else None) or (
                        tool_row["pack_id"] if tool_row else None
                    )
                    call_row = call_rows.get(step_name)
                    entries.append(
                        RunManifestStepEntry(
                            step_id=step_name,
                            agent_id=row["agent_id"],
                            agent_version=agent_row["version"] if agent_row else None,
                            tool_id=row["tool_id"],
                            tool_version=tool_row["version"] if tool_row else None,
                            pack_id=pack_id,
                            pack_version=pack_versions.get(pack_id) if pack_id else None,
                            prompt_id=row["prompt_id"],
                            prompt_version=row["prompt_version"],
                            model_alias=row["model_alias"],
                            resolved_provider=call_row["provider"] if call_row else None,
                            resolved_model_id=call_row["model_id"] if call_row else None,
                        )
                    )

                manifest = RunManifest(
                    workflow_id=workflow_id,
                    workflow_definition_id=definition_id,
                    workflow_definition_version=definition_version,
                    kernel_version=__version__,
                    steps=entries,
                )
                manifest_json = manifest.model_dump(mode="json")
                canonical_json = json.dumps(manifest_json, sort_keys=True).encode("utf-8")
                manifest_hash = f"sha256:{hashlib.sha256(canonical_json).hexdigest()}"
                run_manifest_id = new_run_manifest_id()

                await connection.execute(
                    sa.insert(run_manifests).values(
                        run_manifest_id=run_manifest_id,
                        workflow_id=workflow_id,
                        manifest=manifest_json,
                        manifest_hash=manifest_hash,
                    )
                )
                await connection.execute(
                    sa.update(workflow_instances)
                    .where(workflow_instances.c.workflow_id == workflow_id)
                    .values(run_manifest_id=run_manifest_id)
                )
        except sa.exc.SQLAlchemyError as exc:
            raise RunManifestRecordingError(
                f"failed to record run manifest for workflow '{workflow_id}': {exc}"
            ) from exc
        return run_manifest_id
