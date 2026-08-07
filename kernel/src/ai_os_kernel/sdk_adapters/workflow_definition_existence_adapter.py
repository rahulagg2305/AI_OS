"""The Kernel's own real implementation of the Benchmarking Pack's
`WorkflowDefinitionExistenceCheck` Protocol
(`ai_os_pack_benchmarking.experiment_definition`, `P04-S03-M34-T01`).

**The identical "Kernel implements a Protocol this pack only declares"
shape this package's own docstring already establishes for the SDK's
own Protocols (`llm_gateway_adapter`/`prompt_registry_adapter`/
`tool_invoker_adapter`), applied here to a pack-defined Protocol
instead** — the Benchmarking Pack's own source may not import
`ai_os_kernel` at all (`platform_sdk.md` §9 item 7), so a real
existence check against `catalog.workflow_definitions` cannot live in
that pack; this module is where that real database access happens
instead, on the pack's own behalf.

**A direct, minimal `EXISTS`-shaped query, not
`WorkflowDefinitionCatalog.get()` reused as-is.** `SqlWorkflowDefinitionCatalog.get`
reconstructs a full, real `WorkflowDefinition` from the row's own
`graph` column via `WorkflowDefinition.model_validate(...)` — real,
necessary work for a caller that needs the definition itself, but
wasted work (and a real, avoidable failure mode: a malformed `graph`
this check has no reason to care about) for a caller that only ever
asks "does this pinned `(definition_id, version)` exist at all."

**No real production caller yet** — `P04-S03-M34-T01`'s own scope is
proving `validate_experiment_spec` genuinely rejects a pinned workflow
that does not exist, end to end against a real Postgres. Wiring this
into a real experiment-submission path is later, separate work (the
Benchmarking Pack's own next ticket), the identical "build real, wire
later" precedent already established for the Gate Registry and the
Metrics Collector.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import workflow_definitions


class SqlWorkflowDefinitionExistenceCheck:
    """The only implementation at this stage: SQLAlchemy 2.0 Core
    against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def exists(self, *, definition_id: str, version: str) -> bool:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(sa.literal(1))
                .select_from(workflow_definitions)
                .where(
                    workflow_definitions.c.definition_id == definition_id,
                    workflow_definitions.c.version == version,
                )
                .limit(1)
            )
            return result.first() is not None
