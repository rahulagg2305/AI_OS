"""Real store for ``knowledge.memory_items`` (data_model.md §7,
``P02-S04-M10-T01``) — the smallest real slice: write a memory row and
query it back by structural filters. No schema-authority gap here,
unlike the last two steps: the table, its columns, its `memory_type`
check constraint, and its real FK to
``workflow.workflow_instances.workflow_id`` all already exist, already
documented, already migrated (``0029_knowledge_schema``,
:mod:`ai_os_kernel.persistence.knowledge_schema`) — this module only
adds the write/read path nothing has needed until now.

**Deliberately not placed inside the ``memory_manager`` package**, the
identical reasoning :mod:`ai_os_kernel.persistence.knowledge_writer`
already establishes for ``knowledge.documents``/``knowledge.chunks``:
that package (:mod:`ai_os_kernel.memory_manager`) remains an
intentionally untouched stub, and no owning Memory Manager component
exists yet to claim this. This ticket's own ``module_path`` says
``memory_manager`` — the identical loose, conceptual pointer
``P02-S04-M09-T01``/``T02``'s own tickets already used while landing
in ``persistence/`` too.

**``promoted_at`` is never caller-settable — every new memory starts
unpromoted (``NULL``).** feature_inventory.md's own Memory Manager row
names "promotion logic" as a distinct, unbuilt capability, separate
from the store itself; deciding *when* a memory graduates from
ephemeral to durable is that future mechanism's job, not this writer's.
Accepting a caller-supplied ``promoted_at`` now would mean inventing
that decision's rule ahead of building it.

**``quality_signal``/``expires_at`` are real, optional, caller-supplied
fields — data_model.md §7 already documents both as nullable, and
nothing else in this codebase computes or interprets either yet, so
accepting whatever a caller already knows (or ``None``) is the
"reduced slice" reading, not an invented default.

**``query_memories`` is structural filtering only — no full-text
search.** Unlike ``knowledge.chunks``, ``memory_items`` has no
generated ``tsvector`` column (data_model.md §7 documents none), so
there is nothing for a keyword search to run against yet; filtering by
``memory_type``/``source_workflow_id``, ordered by ``memory_id``
(a sortable ULID — ADR-0022's own "deterministic order" requirement,
the identical tiebreak :class:`~ai_os_kernel.persistence.
knowledge_keyword_search.SqlKeywordSearcher` already uses for ties) is
the smallest real "queryable store" this ticket's own Output asks for.

No update, no delete, no promotion — "prove the store with appropriate
tests," the identical scope discipline :mod:`~ai_os_kernel.persistence.
knowledge_writer` already applied to its own first increment.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_ids import new_memory_id
from ai_os_kernel.persistence.knowledge_schema import memory_items as memory_items_table

MemoryType = Literal["workflow", "engineering", "asset"]


class MemoryWriteError(Exception):
    """A memory item could not be written to or read from
    ``knowledge.memory_items``.

    Raised for both invalid input (e.g. a blank ``content``) and a
    wrapped persistence-layer failure — never a bare stack trace. The
    underlying exception, when there is one, is chained via ``from``.
    """


class MemoryRecord(BaseModel):
    """One ``knowledge.memory_items`` row, as written or read back by
    :class:`SqlMemoryStore`."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    memory_type: MemoryType
    content: str
    source_workflow_id: str
    quality_signal: Decimal | None
    promoted_at: datetime | None
    expires_at: datetime | None
    provenance: dict[str, Any]


class MemoryStore(Protocol):
    """Persistence boundary for writing and querying memory items —
    the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def write_memory(
        self,
        *,
        memory_type: MemoryType,
        content: str,
        source_workflow_id: str,
        quality_signal: Decimal | None = None,
        expires_at: datetime | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> MemoryRecord: ...

    async def query_memories(
        self,
        *,
        memory_type: MemoryType | None = None,
        source_workflow_id: str | None = None,
        limit: int,
    ) -> list[MemoryRecord]: ...


class SqlMemoryStore:
    """The only implementation of :class:`MemoryStore` at this stage:
    SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def write_memory(
        self,
        *,
        memory_type: MemoryType,
        content: str,
        source_workflow_id: str,
        quality_signal: Decimal | None = None,
        expires_at: datetime | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        if not content or not content.strip():
            raise MemoryWriteError("content must not be blank")
        if not source_workflow_id or not source_workflow_id.strip():
            raise MemoryWriteError("source_workflow_id must not be blank")

        record = MemoryRecord(
            memory_id=new_memory_id(),
            memory_type=memory_type,
            content=content,
            source_workflow_id=source_workflow_id,
            quality_signal=quality_signal,
            promoted_at=None,
            expires_at=expires_at,
            provenance=provenance or {},
        )

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(memory_items_table).values(
                        memory_id=record.memory_id,
                        memory_type=record.memory_type,
                        content=record.content,
                        source_workflow_id=record.source_workflow_id,
                        quality_signal=record.quality_signal,
                        promoted_at=record.promoted_at,
                        expires_at=record.expires_at,
                        provenance=record.provenance,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise MemoryWriteError(
                f"failed to write memory item for workflow '{source_workflow_id}': {exc}"
            ) from exc

        return record

    async def query_memories(
        self,
        *,
        memory_type: MemoryType | None = None,
        source_workflow_id: str | None = None,
        limit: int,
    ) -> list[MemoryRecord]:
        if limit <= 0:
            raise MemoryWriteError(f"limit must be positive, got {limit}")

        statement = sa.select(memory_items_table)
        if memory_type is not None:
            statement = statement.where(memory_items_table.c.memory_type == memory_type)
        if source_workflow_id is not None:
            statement = statement.where(
                memory_items_table.c.source_workflow_id == source_workflow_id
            )
        statement = statement.order_by(memory_items_table.c.memory_id.asc()).limit(limit)

        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except sa.exc.SQLAlchemyError as exc:
            raise MemoryWriteError(f"failed to query memory items: {exc}") from exc

        return [MemoryRecord.model_validate(dict(row)) for row in rows]
