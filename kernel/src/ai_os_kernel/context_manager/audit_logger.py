"""The real, persisted Context Audit Logger (``P02-S03-M08-T10``) —
context_manager.md §9's own "record exactly what context was supplied"
requirement (data_model.md §9b: ``context.context_assemblies``).

**Persists exactly what ``ContextRequest``/``AssembledContext`` already
carry — no new computation of its own.** ``sources_queried`` and
``included_items`` are the same real values
:class:`~ai_os_kernel.context_manager.manager.DefaultContextManager.assemble`
already produced; this module's only job is writing them durably.
``included_items`` is stored via each
:class:`~ai_os_kernel.context_manager.models.ContextItem`'s own
``model_dump(mode="json")`` — a lossless, full-fidelity snapshot (not a
summary), the only way this table can genuinely support §9's "exact
replay of experiments."

Two of §9's five named fields are real, disclosed gaps — see
data_model.md §9b for the full reasoning: no ``trace_id`` column (no
``TraceContext`` reaches context assembly anywhere in this codebase),
and no per-excluded-item identity (``AssembledContext`` itself only
ever carries a count).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.context_manager.models import (
    AssembledContext,
    ContextItem,
    ContextRequest,
    SourceType,
)
from ai_os_kernel.context_manager.schema import context_assemblies


class ContextAuditError(Exception):
    """A context assembly could not be recorded or read back — a
    wrapped persistence-layer failure, never a bare stack trace. The
    underlying exception is chained via ``from``.
    """


class ContextAssemblyRecord(BaseModel):
    """One ``context.context_assemblies`` row, read back in full —
    everything needed for exact replay of a past assembly (§9's own
    words)."""

    model_config = ConfigDict(frozen=True)

    assembly_id: str
    workflow_id: str
    step_id: str
    agent_id: str | None
    sources_queried: list[SourceType]
    items: list[ContextItem]
    items_excluded_count: int
    total_tokens: int
    recorded_at: datetime


class ContextAuditLogger(Protocol):
    """Persistence boundary for durably recording one context
    assembly — the seam a fake implementation substitutes in unit
    tests (ADR-0004: interface-driven, configuration over code)."""

    async def record(self, *, request: ContextRequest, assembled: AssembledContext) -> None: ...


class SqlContextAuditLogger:
    """The only implementation of :class:`ContextAuditLogger` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(self, *, request: ContextRequest, assembled: AssembledContext) -> None:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(context_assemblies).values(
                        assembly_id=assembled.assembly_id,
                        workflow_id=request.workflow_id,
                        step_id=request.step_id,
                        agent_id=request.agent_id,
                        sources_queried=[source.value for source in assembled.sources_queried],
                        included_items=[item.model_dump(mode="json") for item in assembled.items],
                        items_excluded_count=assembled.items_excluded_count,
                        total_tokens=assembled.total_tokens,
                        recorded_at=datetime.now(UTC),
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise ContextAuditError(
                f"failed to record context assembly '{assembled.assembly_id}': {exc}"
            ) from exc

    async def get_by_assembly_id(self, assembly_id: str) -> ContextAssemblyRecord | None:
        try:
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            sa.select(context_assemblies).where(
                                context_assemblies.c.assembly_id == assembly_id
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except sa.exc.SQLAlchemyError as exc:
            raise ContextAuditError(
                f"failed to read back context assembly '{assembly_id}': {exc}"
            ) from exc

        if row is None:
            return None

        return ContextAssemblyRecord(
            assembly_id=row["assembly_id"],
            workflow_id=row["workflow_id"],
            step_id=row["step_id"],
            agent_id=row["agent_id"],
            sources_queried=[SourceType(value) for value in row["sources_queried"]],
            items=[ContextItem.model_validate(item) for item in row["included_items"]],
            items_excluded_count=row["items_excluded_count"],
            total_tokens=row["total_tokens"],
            recorded_at=row["recorded_at"],
        )
