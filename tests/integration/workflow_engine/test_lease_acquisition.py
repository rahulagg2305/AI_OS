"""Lease acquisition and release against a real Postgres container
(ADR-0015 — no mocking the database). Proves: a worker can claim a
running instance, a second worker's claim attempt is rejected while
the lease is held, `advance()` works normally with the lease held,
release lets a different worker claim afterward, and an expired lease
can be reclaimed.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_leases
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowLeaseUnavailableError
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.lease_reaper import WorkflowLeaseReaper
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _minimal_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Full Product Creation",
            "description": "Turn a structured specification into working software.",
            "version": _DEFINITION_VERSION,
            "inputs": {
                "type": "object",
                "properties": {"specPath": {"type": "string"}},
                "required": ["specPath"],
            },
            "outputs": {"type": "object"},
            "steps": [
                {
                    "id": "analyze_requirements",
                    "type": "agent",
                    "agentId": "se.software_engineering/analyst",
                }
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


async def _create_running_instance(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        repository = SqlWorkflowInstanceRepository(engine)
        created = await repository.create(
            definition_id=_DEFINITION_ID,
            definition_version=_DEFINITION_VERSION,
            inputs={"specPath": "specs/product.md"},
            principal_id="user-42",
        )
        await repository.transition_to_running(
            workflow_id=created.workflow_id, reason="worker picked it up"
        )
        return created.workflow_id
    finally:
        await engine.dispose()


async def _clear_all_leases(engine: AsyncEngine) -> None:
    """The reaper tests below reason about *all* rows in
    ``workflow_leases`` (bounded scans, exact counts) — a clean slate
    isolates them from other tests in this module-scoped fixture that
    deliberately leave leases (expired or held) behind."""
    async with engine.begin() as connection:
        await connection.execute(sa.delete(workflow_leases))


def test_a_worker_can_acquire_and_release_a_lease(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            lease = await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            assert lease.workflow_id == workflow_id
            assert lease.worker_id == "worker-1"

            await lease_repository.release(workflow_id=workflow_id, worker_id="worker-1")

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(workflow_leases).where(workflow_leases.c.workflow_id == workflow_id)
                )
                assert result.mappings().one_or_none() is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_second_claim_is_rejected_while_the_lease_is_held(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            with pytest.raises(WorkflowLeaseUnavailableError, match="already leased"):
                await lease_repository.acquire(
                    workflow_id=workflow_id, worker_id="worker-2", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_advance_works_normally_while_a_lease_is_held(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                NoOpStepExecutor(),
                SqlWorkflowDefinitionCatalog(engine),
            )
            definition = _minimal_definition()

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            result = await service.advance(workflow_id=workflow_id, definition=definition)

            assert result.current_step_id == "analyze_requirements"

            await lease_repository.release(workflow_id=workflow_id, worker_id="worker-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_release_lets_a_different_worker_claim_afterward(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            await lease_repository.release(workflow_id=workflow_id, worker_id="worker-1")

            second_lease = await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-2", lease_duration_seconds=60
            )

            assert second_lease.worker_id == "worker-2"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_release_by_a_non_holder_is_rejected(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            with pytest.raises(WorkflowLeaseUnavailableError, match="does not hold"):
                await lease_repository.release(workflow_id=workflow_id, worker_id="worker-2")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_acquire_is_rejected_when_the_instance_is_not_running(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            # Still `created`, never transitioned to `running`.
            lease_repository = SqlWorkflowLeaseRepository(engine)

            with pytest.raises(WorkflowLeaseUnavailableError, match="running"):
                await lease_repository.acquire(
                    workflow_id=created.workflow_id, worker_id="worker-1", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_holder_can_renew_the_lease_and_extend_its_expiry(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            original = await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=5
            )

            renewed = await lease_repository.renew(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            assert renewed.lease_id == original.lease_id
            assert renewed.expires_at > original.expires_at
            assert renewed.heartbeat_at >= original.heartbeat_at

            await lease_repository.release(workflow_id=workflow_id, worker_id="worker-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_non_holder_cannot_renew_the_lease(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            with pytest.raises(WorkflowLeaseUnavailableError, match="held by"):
                await lease_repository.renew(
                    workflow_id=workflow_id, worker_id="worker-2", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_renewing_a_lease_that_does_not_exist_is_rejected(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            with pytest.raises(WorkflowLeaseUnavailableError, match="no lease to renew"):
                await lease_repository.renew(
                    workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_renewed_lease_remains_claim_protected_past_its_original_expiry(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=1
            )
            await lease_repository.renew(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            # The *original* 1-second window has now passed, but the
            # renewal pushed expires_at ~60s into the future — a second
            # worker's claim must still be rejected.
            await asyncio.sleep(1.2)

            with pytest.raises(WorkflowLeaseUnavailableError, match="already leased"):
                await lease_repository.acquire(
                    workflow_id=workflow_id, worker_id="worker-2", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_renewing_an_already_expired_lease_is_rejected(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == workflow_id)
                    .values(expires_at=expired)
                )

            with pytest.raises(WorkflowLeaseUnavailableError, match="already expired"):
                await lease_repository.renew(
                    workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_expired_lease_can_be_reclaimed(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            # Acquire, then simulate the crashed worker: force the lease
            # into the past directly, bypassing the repository (which has
            # no "extend/shorten" operation — heartbeat renewal is out of
            # scope for this step).
            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == workflow_id)
                    .values(expires_at=expired)
                )

            reclaimed = await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-2", lease_duration_seconds=60
            )

            assert reclaimed.worker_id == "worker-2"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reap_expired_reclaims_expired_leases_and_leaves_active_ones_untouched(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _clear_all_leases(engine)
            expired_workflow_id = await _create_running_instance(database_url)
            active_workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)

            await lease_repository.acquire(
                workflow_id=expired_workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            await lease_repository.acquire(
                workflow_id=active_workflow_id, worker_id="worker-2", lease_duration_seconds=60
            )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == expired_workflow_id)
                    .values(expires_at=expired)
                )

            reaped = await lease_repository.reap_expired(limit=10)

            assert [lease.workflow_id for lease in reaped] == [expired_workflow_id]

            async with engine.connect() as connection:
                remaining = await connection.execute(sa.select(workflow_leases.c.workflow_id))
                remaining_ids = {row.workflow_id for row in remaining}
            assert remaining_ids == {active_workflow_id}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reap_expired_is_bounded_by_the_caller_supplied_limit(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _clear_all_leases(engine)
            workflow_ids = [await _create_running_instance(database_url) for _ in range(3)]
            lease_repository = SqlWorkflowLeaseRepository(engine)
            for index, workflow_id in enumerate(workflow_ids):
                await lease_repository.acquire(
                    workflow_id=workflow_id,
                    worker_id=f"worker-{index}",
                    lease_duration_seconds=60,
                )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id.in_(workflow_ids))
                    .values(expires_at=expired)
                )

            first_batch = await lease_repository.reap_expired(limit=2)
            assert len(first_batch) == 2

            async with engine.connect() as connection:
                remaining = await connection.execute(sa.select(workflow_leases.c.workflow_id))
                remaining_ids = {row.workflow_id for row in remaining}
            assert len(remaining_ids) == 1

            second_batch = await lease_repository.reap_expired(limit=10)
            assert len(second_batch) == 1

            async with engine.connect() as connection:
                after_second_pass = await connection.execute(
                    sa.select(workflow_leases.c.workflow_id)
                )
                assert after_second_pass.mappings().all() == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_reaper_job_reclaims_an_expired_lease_via_the_service(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _clear_all_leases(engine)
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)
            reaper = WorkflowLeaseReaper(WorkflowLeaseService(lease_repository))

            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == workflow_id)
                    .values(expires_at=expired)
                )

            result = await reaper.reap_once(limit=10)

            assert result.count == 1
            assert result.reaped[0].workflow_id == workflow_id

            async with engine.connect() as connection:
                still_there = await connection.execute(
                    sa.select(workflow_leases).where(workflow_leases.c.workflow_id == workflow_id)
                )
                assert still_there.mappings().one_or_none() is None
        finally:
            await engine.dispose()

    asyncio.run(_run())
