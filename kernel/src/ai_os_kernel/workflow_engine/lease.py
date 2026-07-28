"""Lease acquisition and release against ``workflow.workflow_leases``.

data_model.md §4.4: "Claimed with ``SELECT … FOR UPDATE SKIP LOCKED``.
This table is what lets multiple workers run without a broker; expiry
is what makes a crashed worker's work recoverable" (ADR-0020).
workflow_engine.md §7.1: "A worker claims an instance with
``SELECT … FOR UPDATE SKIP LOCKED``, then heartbeats. A lease that
expires without a heartbeat is reclaimed by another worker."

Acquire is a single transaction:

1. The target instance must exist and be ``running`` — leasing anything
   else is meaningless.
2. If no lease row exists yet for this ``workflow_id``, insert one
   (``INSERT ... ON CONFLICT (workflow_id) DO NOTHING``) — the common
   case, no contention.
3. If a row already exists, it can only be *reclaimed* if it is
   expired, and the reclaim ``SELECT`` uses ``FOR UPDATE SKIP LOCKED``:
   a concurrent claimant racing for the same row is rejected
   immediately (no row returned) rather than blocked until the other
   transaction commits.

Release deletes the lease row — the caller must be the worker that
holds it.

Renewal (``renew``) extends ``expires_at``/``heartbeat_at`` on a lease
the calling worker still holds. It is one atomic guarded
``UPDATE ... WHERE workflow_id = :id AND worker_id = :worker_id AND
expires_at >= now() RETURNING *`` — the same "the guard is the WHERE
clause" pattern used everywhere else in this module and in
:mod:`ai_os_kernel.workflow_engine.repository`. ``FOR UPDATE SKIP
LOCKED`` (used in ``acquire``'s reclaim step) is for scanning an
*unknown* row's current state before deciding whether to act on it;
renewal already knows exactly which row it means to update and what
condition it must satisfy, so the guarded ``UPDATE`` itself is the
correct, sufficient atomic primitive — Postgres's ordinary row lock
during the ``UPDATE`` already serialises it against a concurrent
``acquire`` reclaim attempt on the same row.

``reap_expired`` proactively reclaims leases past ``expires_at``
without waiting for another worker's ``acquire`` call to trigger a
reclaim — the one remaining reactive gap in the acquire → renew →
release → reclaim cycle. It scans for candidate rows with
``SELECT ... FOR UPDATE SKIP LOCKED`` (the same "scanning an unknown
row's state" reasoning as ``acquire``'s reclaim step: a row currently
being touched by a concurrent ``acquire``/``renew``/``release`` is
skipped this pass rather than blocked on), then deletes exactly the
rows it locked, bounded by a caller-supplied ``limit``.
:mod:`ai_os_kernel.workflow_engine.lease_reaper` wraps this in a small,
structured-logging job; deciding when/how often to run it remains a
future worker process framework's job, not this module's.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_os_kernel.persistence.schema import workflow_instances, workflow_leases
from ai_os_kernel.workflow_engine.errors import WorkflowLeaseUnavailableError
from ai_os_kernel.workflow_engine.ids import new_lease_id
from ai_os_kernel.workflow_engine.input_validation import (
    validate_lease_duration,
    validate_reap_limit,
    validate_worker_id,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus


class WorkflowLease(BaseModel):
    """One ``workflow_leases`` row, as read back immediately after
    acquisition."""

    model_config = ConfigDict(frozen=True)

    lease_id: str
    workflow_id: str
    worker_id: str
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime


class WorkflowLeaseRepository(Protocol):
    """Persistence boundary for lease acquisition and release — the
    seam a fake/in-memory implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease: ...

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease: ...

    async def release(self, *, workflow_id: str, worker_id: str) -> None: ...

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]: ...


class SqlWorkflowLeaseRepository:
    """The only implementation of :class:`WorkflowLeaseRepository` at
    this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=lease_duration_seconds)

        try:
            async with self._engine.begin() as connection:
                status_result = await connection.execute(
                    sa.select(workflow_instances.c.status).where(
                        workflow_instances.c.workflow_id == workflow_id
                    )
                )
                status = status_result.scalar_one_or_none()
                if status is None:
                    raise WorkflowLeaseUnavailableError(
                        f"workflow instance '{workflow_id}' does not exist"
                    )
                if status != WorkflowInstanceStatus.RUNNING.value:
                    raise WorkflowLeaseUnavailableError(
                        f"workflow instance '{workflow_id}' cannot be leased: "
                        f"status is '{status}', not 'running'"
                    )

                inserted = await connection.execute(
                    pg_insert(workflow_leases)
                    .values(
                        lease_id=new_lease_id(),
                        workflow_id=workflow_id,
                        worker_id=worker_id,
                        acquired_at=now,
                        expires_at=expires_at,
                        heartbeat_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["workflow_id"])
                    .returning(*workflow_leases.columns)
                )
                inserted_row = inserted.mappings().one_or_none()
                if inserted_row is not None:
                    return WorkflowLease.model_validate(dict(inserted_row))

                # A lease row already exists. It can only be reclaimed if
                # expired; FOR UPDATE SKIP LOCKED means a concurrent
                # claimant racing for this same row gets no row back
                # immediately, instead of blocking on the other
                # transaction.
                reclaimable = await connection.execute(
                    sa.select(workflow_leases)
                    .where(
                        workflow_leases.c.workflow_id == workflow_id,
                        workflow_leases.c.expires_at < now,
                    )
                    .with_for_update(skip_locked=True)
                )
                reclaimable_row = reclaimable.mappings().one_or_none()
                if reclaimable_row is None:
                    raise WorkflowLeaseUnavailableError(
                        f"workflow instance '{workflow_id}' is already leased and not "
                        "yet expired, or is currently being claimed by another worker"
                    )

                updated = await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == workflow_id)
                    .values(
                        worker_id=worker_id,
                        acquired_at=now,
                        expires_at=expires_at,
                        heartbeat_at=now,
                    )
                    .returning(*workflow_leases.columns)
                )
                updated_row = updated.mappings().one()
                return WorkflowLease.model_validate(dict(updated_row))
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowLeaseUnavailableError(
                f"failed to acquire lease for workflow instance '{workflow_id}': {exc}"
            ) from exc

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        now = datetime.now(UTC)
        new_expires_at = now + timedelta(seconds=lease_duration_seconds)

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.update(workflow_leases)
                    .where(
                        workflow_leases.c.workflow_id == workflow_id,
                        workflow_leases.c.worker_id == worker_id,
                        workflow_leases.c.expires_at >= now,
                    )
                    .values(expires_at=new_expires_at, heartbeat_at=now)
                    .returning(*workflow_leases.columns)
                )
                row = result.mappings().one_or_none()
                if row is None:
                    raise WorkflowLeaseUnavailableError(
                        await self._describe_rejected_renewal(connection, workflow_id, worker_id)
                    )
                return WorkflowLease.model_validate(dict(row))
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowLeaseUnavailableError(
                f"failed to renew lease for workflow instance '{workflow_id}': {exc}"
            ) from exc

    async def release(self, *, workflow_id: str, worker_id: str) -> None:
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.delete(workflow_leases).where(
                        workflow_leases.c.workflow_id == workflow_id,
                        workflow_leases.c.worker_id == worker_id,
                    )
                )
                if result.rowcount == 0:
                    raise WorkflowLeaseUnavailableError(
                        f"worker '{worker_id}' does not hold a lease on workflow "
                        f"instance '{workflow_id}' — nothing to release"
                    )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowLeaseUnavailableError(
                f"failed to release lease for workflow instance '{workflow_id}': {exc}"
            ) from exc

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]:
        now = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                candidates = await connection.execute(
                    sa.select(workflow_leases.c.lease_id)
                    .where(workflow_leases.c.expires_at < now)
                    .order_by(workflow_leases.c.expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                lease_ids = [row.lease_id for row in candidates]
                if not lease_ids:
                    return []

                deleted = await connection.execute(
                    sa.delete(workflow_leases)
                    .where(workflow_leases.c.lease_id.in_(lease_ids))
                    .returning(*workflow_leases.columns)
                )
                return [WorkflowLease.model_validate(dict(row)) for row in deleted.mappings().all()]
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowLeaseUnavailableError(f"failed to reap expired leases: {exc}") from exc

    @staticmethod
    async def _describe_rejected_renewal(
        connection: AsyncConnection, workflow_id: str, worker_id: str
    ) -> str:
        current = await connection.execute(
            sa.select(workflow_leases.c.worker_id, workflow_leases.c.expires_at).where(
                workflow_leases.c.workflow_id == workflow_id
            )
        )
        row = current.mappings().one_or_none()
        if row is None:
            return f"workflow instance '{workflow_id}' has no lease to renew"
        if row["worker_id"] != worker_id:
            return (
                f"worker '{worker_id}' does not hold the lease on workflow instance "
                f"'{workflow_id}' — it is held by '{row['worker_id']}'"
            )
        return (
            f"worker '{worker_id}'s lease on workflow instance '{workflow_id}' already "
            f"expired at {row['expires_at'].isoformat()} — it may have been reclaimed "
            "by another worker"
        )


class WorkflowLeaseService:
    """Validates, then delegates to the injected
    :class:`WorkflowLeaseRepository` (ADR-0010: no DI container — the
    concrete repository is constructed and handed in by whatever wires
    this service up)."""

    def __init__(self, repository: WorkflowLeaseRepository) -> None:
        self._repository = repository

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        validate_worker_id(worker_id)
        validate_lease_duration(lease_duration_seconds)
        return await self._repository.acquire(
            workflow_id=workflow_id,
            worker_id=worker_id,
            lease_duration_seconds=lease_duration_seconds,
        )

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        validate_worker_id(worker_id)
        validate_lease_duration(lease_duration_seconds)
        return await self._repository.renew(
            workflow_id=workflow_id,
            worker_id=worker_id,
            lease_duration_seconds=lease_duration_seconds,
        )

    async def release(self, *, workflow_id: str, worker_id: str) -> None:
        validate_worker_id(worker_id)
        await self._repository.release(workflow_id=workflow_id, worker_id=worker_id)

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]:
        validate_reap_limit(limit)
        return await self._repository.reap_expired(limit=limit)
