"""Unit tests for WorkflowLeaseReaper: bounded reap-once delegation to
a real WorkflowLeaseService backed by a fake repository — no database
(ADR-0004: interface-driven, so a fake Protocol implementation is a
legitimate substitute in a unit test)."""

from datetime import UTC, datetime

import pytest

from ai_os_kernel.workflow_engine.errors import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.lease import WorkflowLease, WorkflowLeaseService
from ai_os_kernel.workflow_engine.lease_reaper import WorkflowLeaseReaper


def _lease(lease_id: str, workflow_id: str) -> WorkflowLease:
    now = datetime.now(UTC)
    return WorkflowLease(
        lease_id=lease_id,
        workflow_id=workflow_id,
        worker_id="worker-1",
        acquired_at=now,
        expires_at=now,
        heartbeat_at=now,
    )


class _FakeLeaseRepository:
    def __init__(self, *, expired_leases: list[WorkflowLease]) -> None:
        self._expired_leases = list(expired_leases)
        self.reap_expired_calls: list[dict[str, object]] = []

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        raise NotImplementedError

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        raise NotImplementedError

    async def release(self, *, workflow_id: str, worker_id: str) -> None:
        raise NotImplementedError

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]:
        self.reap_expired_calls.append({"limit": limit})
        batch = self._expired_leases[:limit]
        del self._expired_leases[:limit]
        return batch


@pytest.mark.asyncio
async def test_reap_once_returns_and_logs_the_reclaimed_leases() -> None:
    expired = [_lease("lease_1", "wf_1"), _lease("lease_2", "wf_2")]
    repository = _FakeLeaseRepository(expired_leases=expired)
    reaper = WorkflowLeaseReaper(WorkflowLeaseService(repository))

    result = await reaper.reap_once(limit=10)

    assert result.count == 2
    assert result.reaped == tuple(expired)
    assert repository.reap_expired_calls == [{"limit": 10}]


@pytest.mark.asyncio
async def test_reap_once_with_no_expired_leases_returns_an_empty_result() -> None:
    repository = _FakeLeaseRepository(expired_leases=[])
    reaper = WorkflowLeaseReaper(WorkflowLeaseService(repository))

    result = await reaper.reap_once(limit=10)

    assert result.count == 0
    assert result.reaped == ()


@pytest.mark.asyncio
async def test_reap_once_respects_the_limit_across_more_candidates_than_the_bound() -> None:
    expired = [_lease("lease_1", "wf_1"), _lease("lease_2", "wf_2"), _lease("lease_3", "wf_3")]
    repository = _FakeLeaseRepository(expired_leases=expired)
    reaper = WorkflowLeaseReaper(WorkflowLeaseService(repository))

    result = await reaper.reap_once(limit=2)

    assert result.count == 2
    assert repository.reap_expired_calls == [{"limit": 2}]


@pytest.mark.asyncio
async def test_non_positive_limit_is_rejected_before_the_repository_is_called() -> None:
    repository = _FakeLeaseRepository(expired_leases=[])
    reaper = WorkflowLeaseReaper(WorkflowLeaseService(repository))

    with pytest.raises(WorkflowInputValidationError, match="limit"):
        await reaper.reap_once(limit=0)

    assert repository.reap_expired_calls == []
