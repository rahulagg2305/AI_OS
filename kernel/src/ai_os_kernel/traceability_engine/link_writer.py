"""The ``trace.links`` writer (``P04-S02-M16-T01``, FR-019,
data_model.md §8) — this table's first real writer. Until now nothing
computed an ``artifact_key``, upserted a ``trace.artifacts`` row, or
inserted a ``trace.links`` row at all (both modules' own docstrings:
"Schema and migration only — no writer").

**The one real design decision this ticket needed a product-owner
call on**: ``trace.links.source_key``/``target_key`` are foreign keys
into ``trace.artifacts``, and nothing else in this codebase creates an
artifact row — so a links writer alone would have nothing real to
reference. Presented two options: mint a random key per artifact
(mirroring every other id in this codebase) and require callers to
create-then-remember it, or resolve/upsert both endpoint artifacts
*inline*, keyed deterministically off their own real-world identity
(``artifact_type``/``external_id``) — so two independent callers (a
Documentation Agent today, a QA Agent tomorrow) both naming requirement
``FR-019`` land on the identical row with no shared state. The product
owner chose the deterministic form; see
:func:`~ai_os_kernel.traceability_engine.ids.compute_artifact_key`.

**Re-asserting an already-open, identical ``(source_key, relationship,
target_key)`` triple is idempotent, not an error.** A real caller (an
agent re-running the same real analysis) should not fail on its second
call just because the first one already recorded the identical link —
:meth:`SqlTraceLinkWriter.record_link` returns the existing open link
unchanged rather than racing the schema's own partial unique index
(data_model.md §8: ``UNIQUE (source_key, relationship, target_key)
WHERE closed_at IS NULL``) into an ``IntegrityError``.

**Closing is real too, not deferred**, closing traceability_model.md
§6's own rule ("when artifacts are superseded, related links must be
... closed") — a links writer that can only ever open links is only
half a writer.

**Query/impact-analysis is deliberately out of scope** — ``Impact
query`` (``P04-S02-M16-T02``) and ``Coverage query`` (``P04-S02-M16-T03``)
are this ticket's own, separate, already-recorded dependents;
:meth:`SqlTraceLinkWriter.get_open_link` exists only because
:meth:`record_link`'s own idempotency check needs it internally, not as
a general query API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_os_kernel.persistence.trace_schema import (
    ARTIFACT_TYPES,
    LINK_CONFIDENCES,
    LINK_CREATED_BY_TYPES,
    LINK_RELATIONSHIPS,
    artifacts,
    links,
)
from ai_os_kernel.traceability_engine.errors import (
    TraceabilityError,
    TraceabilityValidationError,
    TraceLinkNotFoundError,
)
from ai_os_kernel.traceability_engine.ids import compute_artifact_key, new_link_id
from ai_os_kernel.traceability_engine.models import ArtifactInput, TraceLink


def _validate_in(value: str, *, valid: tuple[str, ...], field_name: str) -> None:
    """Raises before any real database call — a caller gets a clear
    message instead of a raw ``CHECK`` constraint failure (mirrors
    :class:`~ai_os_kernel.observability.audit.AuditOutcome`'s own
    reasoning, applied to a plain ``str`` field here since
    data_model.md §8 defines these as ``TEXT`` + ``CHECK``, never a
    Python enum)."""
    if value not in valid:
        raise TraceabilityValidationError(f"{field_name}={value!r} is not one of {valid}")


class TraceLinkWriter(Protocol):
    """Persistence boundary for recording/closing a traceability link
    — the seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def record_link(
        self,
        *,
        source: ArtifactInput,
        relationship: str,
        target: ArtifactInput,
        confidence: str,
        created_by: str,
        created_by_type: str,
    ) -> TraceLink: ...

    async def close_link(self, *, link_id: str) -> TraceLink: ...

    async def get_open_link(
        self, *, source_key: str, relationship: str, target_key: str
    ) -> TraceLink | None: ...


class SqlTraceLinkWriter:
    """The only implementation of :class:`TraceLinkWriter` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record_link(
        self,
        *,
        source: ArtifactInput,
        relationship: str,
        target: ArtifactInput,
        confidence: str,
        created_by: str,
        created_by_type: str,
    ) -> TraceLink:
        _validate_in(source.artifact_type, valid=ARTIFACT_TYPES, field_name="source.artifact_type")
        _validate_in(target.artifact_type, valid=ARTIFACT_TYPES, field_name="target.artifact_type")
        _validate_in(relationship, valid=LINK_RELATIONSHIPS, field_name="relationship")
        _validate_in(confidence, valid=LINK_CONFIDENCES, field_name="confidence")
        _validate_in(created_by_type, valid=LINK_CREATED_BY_TYPES, field_name="created_by_type")

        source_key = compute_artifact_key(
            artifact_type=source.artifact_type, external_id=source.external_id
        )
        target_key = compute_artifact_key(
            artifact_type=target.artifact_type, external_id=target.external_id
        )

        try:
            async with self._engine.begin() as connection:
                await self._upsert_artifact(connection, key=source_key, artifact=source)
                await self._upsert_artifact(connection, key=target_key, artifact=target)

                existing = await self._select_open_link(
                    connection,
                    source_key=source_key,
                    relationship=relationship,
                    target_key=target_key,
                )
                if existing is not None:
                    return existing

                link_id = new_link_id()
                created_at = datetime.now(UTC)
                await connection.execute(
                    sa.insert(links).values(
                        link_id=link_id,
                        source_key=source_key,
                        relationship=relationship,
                        target_key=target_key,
                        confidence=confidence,
                        created_by=created_by,
                        created_by_type=created_by_type,
                        created_at=created_at,
                        closed_at=None,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise TraceabilityError(
                f"failed to record link {source_key!r} -{relationship}-> {target_key!r}: {exc}"
            ) from exc

        return TraceLink(
            link_id=link_id,
            source_key=source_key,
            relationship=relationship,
            target_key=target_key,
            confidence=confidence,
            created_by=created_by,
            created_by_type=created_by_type,
            created_at=created_at,
            closed_at=None,
        )

    async def _upsert_artifact(
        self, connection: AsyncConnection, *, key: str, artifact: ArtifactInput
    ) -> None:
        upsert = pg_insert(artifacts).values(
            artifact_key=key,
            artifact_type=artifact.artifact_type,
            external_id=artifact.external_id,
            title=artifact.title,
            location=artifact.location,
            version=artifact.version,
        )
        await connection.execute(
            upsert.on_conflict_do_update(
                index_elements=["artifact_key"],
                set_={
                    "title": upsert.excluded.title,
                    "location": upsert.excluded.location,
                    "version": upsert.excluded.version,
                },
            )
        )

    async def _select_open_link(
        self,
        connection: AsyncConnection,
        *,
        source_key: str,
        relationship: str,
        target_key: str,
    ) -> TraceLink | None:
        row = (
            (
                await connection.execute(
                    sa.select(links).where(
                        links.c.source_key == source_key,
                        links.c.relationship == relationship,
                        links.c.target_key == target_key,
                        links.c.closed_at.is_(None),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return TraceLink.model_validate(dict(row)) if row is not None else None

    async def get_open_link(
        self, *, source_key: str, relationship: str, target_key: str
    ) -> TraceLink | None:
        async with self._engine.connect() as connection:
            return await self._select_open_link(
                connection, source_key=source_key, relationship=relationship, target_key=target_key
            )

    async def close_link(self, *, link_id: str) -> TraceLink:
        closed_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(links)
                    .where(links.c.link_id == link_id, links.c.closed_at.is_(None))
                    .values(closed_at=closed_at)
                )
                if result.rowcount == 0:
                    raise TraceLinkNotFoundError(
                        f"link_id {link_id!r} does not exist or is already closed"
                    )
                row = (
                    (await connection.execute(sa.select(links).where(links.c.link_id == link_id)))
                    .mappings()
                    .one()
                )
        except sa.exc.SQLAlchemyError as exc:
            raise TraceabilityError(f"failed to close link {link_id!r}: {exc}") from exc
        return TraceLink.model_validate(dict(row))
