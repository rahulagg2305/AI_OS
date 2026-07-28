"""Unit tests for WorkflowLeaseService: validate-then-delegate, with a
fake repository — no database (ADR-0004: interface-driven, so a fake
Protocol implementation is a legitimate substitute in a unit test)."""

from datetime import UTC, datetime

import pytest

from ai_os_kernel.workflow_engine.errors import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.lease import WorkflowLease, WorkflowLeaseService


class _FakeLeaseRepository:
    def __init__(self, *, expired_leases: list[WorkflowLease] | None = None) -> None:
        self.acquire_calls: list[dict[str, object]] = []
        self.renew_calls: list[dict[str, object]] = []
        self.release_calls: list[dict[str, object]] = []
        self.reap_expired_calls: list[dict[str, object]] = []
        self._expired_leases = expired_leases or []

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        self.acquire_calls.append(
            {
                "workflow_id": workflow_id,
                "worker_id": worker_id,
                "lease_duration_seconds": lease_duration_seconds,
            }
        )
        now = datetime.now(UTC)
        return WorkflowLease(
            lease_id="lease_fake",
            workflow_id=workflow_id,
            worker_id=worker_id,
            acquired_at=now,
            expires_at=now,
            heartbeat_at=now,
        )

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        self.renew_calls.append(
            {
                "workflow_id": workflow_id,
                "worker_id": worker_id,
                "lease_duration_seconds": lease_duration_seconds,
            }
        )
        now = datetime.now(UTC)
        return WorkflowLease(
            lease_id="lease_fake",
            workflow_id=workflow_id,
            worker_id=worker_id,
            acquired_at=now,
            expires_at=now,
            heartbeat_at=now,
        )

    async def release(self, *, workflow_id: str, worker_id: str) -> None:
        self.release_calls.append({"workflow_id": workflow_id, "worker_id": worker_id})

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]:
        self.reap_expired_calls.append({"limit": limit})
        return self._expired_leases[:limit]


@pytest.mark.asyncio
async def test_acquire_is_delegated_to_the_repository() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    lease = await service.acquire(
        workflow_id="wf_fake", worker_id="worker-1", lease_duration_seconds=60
    )

    assert lease.workflow_id == "wf_fake"
    assert lease.worker_id == "worker-1"
    assert repository.acquire_calls == [
        {"workflow_id": "wf_fake", "worker_id": "worker-1", "lease_duration_seconds": 60}
    ]


@pytest.mark.asyncio
async def test_renew_is_delegated_to_the_repository() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    lease = await service.renew(
        workflow_id="wf_fake", worker_id="worker-1", lease_duration_seconds=30
    )

    assert lease.workflow_id == "wf_fake"
    assert repository.renew_calls == [
        {"workflow_id": "wf_fake", "worker_id": "worker-1", "lease_duration_seconds": 30}
    ]


@pytest.mark.asyncio
async def test_release_is_delegated_to_the_repository() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    await service.release(workflow_id="wf_fake", worker_id="worker-1")

    assert repository.release_calls == [{"workflow_id": "wf_fake", "worker_id": "worker-1"}]


@pytest.mark.asyncio
async def test_blank_worker_id_is_rejected_before_acquire() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="worker_id"):
        await service.acquire(workflow_id="wf_fake", worker_id="   ", lease_duration_seconds=60)

    assert repository.acquire_calls == []


@pytest.mark.asyncio
async def test_blank_worker_id_is_rejected_before_renew() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="worker_id"):
        await service.renew(workflow_id="wf_fake", worker_id="   ", lease_duration_seconds=60)

    assert repository.renew_calls == []


@pytest.mark.asyncio
async def test_blank_worker_id_is_rejected_before_release() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="worker_id"):
        await service.release(workflow_id="wf_fake", worker_id="")

    assert repository.release_calls == []


@pytest.mark.asyncio
async def test_non_positive_lease_duration_is_rejected_before_acquire() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="lease_duration_seconds"):
        await service.acquire(workflow_id="wf_fake", worker_id="worker-1", lease_duration_seconds=0)

    assert repository.acquire_calls == []


@pytest.mark.asyncio
async def test_non_positive_lease_duration_is_rejected_before_renew() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="lease_duration_seconds"):
        await service.renew(workflow_id="wf_fake", worker_id="worker-1", lease_duration_seconds=-1)

    assert repository.renew_calls == []


@pytest.mark.asyncio
async def test_reap_expired_is_delegated_to_the_repository() -> None:
    now = datetime.now(UTC)
    expired = WorkflowLease(
        lease_id="lease_expired",
        workflow_id="wf_fake",
        worker_id="worker-1",
        acquired_at=now,
        expires_at=now,
        heartbeat_at=now,
    )
    repository = _FakeLeaseRepository(expired_leases=[expired])
    service = WorkflowLeaseService(repository)

    reaped = await service.reap_expired(limit=10)

    assert reaped == [expired]
    assert repository.reap_expired_calls == [{"limit": 10}]


@pytest.mark.asyncio
async def test_non_positive_reap_limit_is_rejected_before_the_repository_is_called() -> None:
    repository = _FakeLeaseRepository()
    service = WorkflowLeaseService(repository)

    with pytest.raises(WorkflowInputValidationError, match="limit"):
        await service.reap_expired(limit=0)

    assert repository.reap_expired_calls == []
