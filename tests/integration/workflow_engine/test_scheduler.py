"""Real proof of ``WorkflowInstanceRepository.list_startable_instances``/
``WorkflowScheduler.tick_once`` against a real Postgres container
(ADR-0015 — no mocking the database), isolated from the full
``_lifespan`` composition ``tests/integration/test_scheduler_in_lifespan.py``
already proves end to end. Proves: an instance with a real, due
``scheduled_at`` is genuinely discovered and started; one with no
``scheduled_at``, or a not-yet-due one, is genuinely left alone; and a
race with another caller that already started the same instance first
is a real, isolated skip, never a per-tick failure.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.scheduler import WorkflowScheduler
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


async def _create(
    repository: SqlWorkflowInstanceRepository, *, scheduled_at: datetime | None
) -> str:
    created = await repository.create(
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        inputs={},
        principal_id="user-42",
        scheduled_at=scheduled_at,
    )
    return created.workflow_id


def test_list_startable_instances_finds_only_due_scheduled_instances(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            now = datetime.now(UTC)

            due_id = await _create(repository, scheduled_at=now - timedelta(seconds=5))
            not_due_id = await _create(repository, scheduled_at=now + timedelta(hours=1))
            unscheduled_id = await _create(repository, scheduled_at=None)

            found = await repository.list_startable_instances(limit=100)
            found_ids = {instance.workflow_id for instance in found}

            assert due_id in found_ids
            assert not_due_id not in found_ids
            assert unscheduled_id not in found_ids
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_tick_once_starts_every_due_instance_and_leaves_others_alone(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            now = datetime.now(UTC)

            due_id = await _create(repository, scheduled_at=now - timedelta(seconds=5))
            not_due_id = await _create(repository, scheduled_at=now + timedelta(hours=1))

            result = await WorkflowScheduler(repository).tick_once(limit=100)

            assert due_id in result.started
            assert not_due_id not in result.started

            due_instance = await repository.get_instance(due_id)
            not_due_instance = await repository.get_instance(not_due_id)
            assert due_instance is not None
            assert due_instance.status == WorkflowInstanceStatus.RUNNING
            assert not_due_instance is not None
            assert not_due_instance.status == WorkflowInstanceStatus.CREATED
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_tick_once_treats_an_already_started_instance_as_a_skip_not_a_failure(
    database_url: str,
) -> None:
    """Isolates the real race this module's own docstring names: some
    other caller (a real HTTP start, or a second scheduler tick) already
    moved the instance to ``running`` before this tick's own
    ``transition_to_running`` call runs — a genuine, expected skip."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            due_id = await _create(
                repository, scheduled_at=datetime.now(UTC) - timedelta(seconds=5)
            )
            # Simulate the race: some other real caller starts it first.
            await repository.transition_to_running(workflow_id=due_id, reason="raced start")

            result = await WorkflowScheduler(repository).tick_once(limit=100)

            assert due_id not in result.started
            instance = await repository.get_instance(due_id)
            assert instance is not None
            assert instance.status == WorkflowInstanceStatus.RUNNING
        finally:
            await engine.dispose()

    asyncio.run(_run())
