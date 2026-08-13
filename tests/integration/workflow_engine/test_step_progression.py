"""Multi-step progression against a real Postgres container (ADR-0015 —
no mocking the database). Proves: first step, then second step, then
completion, each in its own transaction; invalid calls (not running,
already completed, stale current-step expectation) are rejected without
side effects; and a failure in the completion event insert rolls back
the status change that had already "succeeded" earlier in the same
transaction.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_instances, workflow_steps
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import (
    WorkflowInstanceCreationError,
    WorkflowInvalidTransitionError,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
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
                },
                {"id": "implement", "type": "agent", "agentId": "se.software_engineering/analyst"},
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


async def _fetch_instance(database_url: str, workflow_id: str) -> dict[str, Any] | None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_instances).where(workflow_instances.c.workflow_id == workflow_id)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


async def _fetch_events(database_url: str, workflow_id: str) -> list[dict[str, Any]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text(
                    "SELECT seq, event_type, step_id, payload FROM workflow.workflow_events "
                    "WHERE workflow_id = :workflow_id ORDER BY seq"
                ),
                {"workflow_id": workflow_id},
            )
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


async def _fetch_workflow_steps(database_url: str, workflow_id: str) -> list[dict[str, Any]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_steps)
                .where(workflow_steps.c.workflow_id == workflow_id)
                .order_by(workflow_steps.c.started_at)
            )
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


def test_service_advances_first_then_second_step_then_completes(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                NoOpStepExecutor(),
                SqlWorkflowDefinitionCatalog(engine),
            )
            definition = _minimal_definition()

            created = await service.create_instance(
                definition=definition,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
                pack_id="se.software_engineering",
            )
            await service.start(workflow_id=created.workflow_id, reason="worker picked it up")

            after_first = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_first.status == WorkflowInstanceStatus.RUNNING
            assert after_first.current_step_id == "analyze_requirements"
            assert after_first.last_event_seq == 4

            after_second = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_second.status == WorkflowInstanceStatus.RUNNING
            assert after_second.current_step_id == "implement"
            assert after_second.last_event_seq == 6

            after_completion = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_completion.status == WorkflowInstanceStatus.COMPLETED
            assert after_completion.completed_at is not None
            assert after_completion.last_event_seq == 7

            stored = await _fetch_instance(database_url, created.workflow_id)
            assert stored is not None
            assert stored["status"] == "completed"
            assert stored["completed_at"] is not None

            events = await _fetch_events(database_url, created.workflow_id)
            assert [e["event_type"] for e in events] == [
                "workflow.started",
                "state.transitioned",
                "step.started",
                "step.completed",
                "step.started",
                "step.completed",
                "workflow.completed",
            ]
            assert events[2]["step_id"] == "analyze_requirements"
            assert events[4]["step_id"] == "implement"
            assert events[6]["step_id"] is None
            assert events[6]["payload"] == {}

            steps = await _fetch_workflow_steps(database_url, created.workflow_id)
            assert [s["step_name"] for s in steps] == ["analyze_requirements", "implement"]
            for step_row in steps:
                assert step_row["step_type"] == "agent"
                assert step_row["status"] == "completed"
                assert step_row["attempt"] == 1
                assert step_row["outputs"] == {}
                assert step_row["started_at"] is not None
                assert step_row["completed_at"] is not None
            assert steps[0]["idempotency_key"] == f"{created.workflow_id}:analyze_requirements:1"
            assert steps[1]["idempotency_key"] == f"{created.workflow_id}:implement:1"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_advance_is_rejected_when_instance_is_not_running(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                NoOpStepExecutor(),
                SqlWorkflowDefinitionCatalog(engine),
            )
            definition = _minimal_definition()
            created = await service.create_instance(
                definition=definition,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
                pack_id="se.software_engineering",
            )
            # Never transitioned to `running`.

            with pytest.raises(WorkflowInvalidTransitionError, match="running"):
                await service.advance(workflow_id=created.workflow_id, definition=definition)

            events = await _fetch_events(database_url, created.workflow_id)
            assert len(events) == 1  # only workflow.started
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_advance_is_rejected_when_the_workflow_already_completed(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                NoOpStepExecutor(),
                SqlWorkflowDefinitionCatalog(engine),
            )
            definition = _minimal_definition()
            created = await service.create_instance(
                definition=definition,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
                pack_id="se.software_engineering",
            )
            await service.start(workflow_id=created.workflow_id, reason="worker picked it up")
            await service.advance(workflow_id=created.workflow_id, definition=definition)
            await service.advance(workflow_id=created.workflow_id, definition=definition)
            completed = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert completed.status == WorkflowInstanceStatus.COMPLETED

            with pytest.raises(WorkflowInvalidTransitionError, match="running"):
                await service.advance(workflow_id=created.workflow_id, definition=definition)

            events = await _fetch_events(database_url, created.workflow_id)
            assert len(events) == 7  # unchanged by the rejected extra call
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_advance_is_rejected_on_a_stale_current_step_expectation(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            definition = _minimal_definition()
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id=None,
                next_step=definition.steps[0],
                outputs={},
            )

            # A stale caller still believes current_step_id is None
            # (i.e. it read the instance before the advance above).
            with pytest.raises(WorkflowInvalidTransitionError, match="already advanced"):
                await repository.advance_workflow(
                    workflow_id=created.workflow_id,
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    expected_current_step_id=None,
                    next_step=definition.steps[0],
                    outputs={},
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_completion_event_insert_rolls_back_the_status_change(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            definition = _minimal_definition()
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id=None,
                next_step=definition.steps[0],
                outputs={},
            )
            await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id="analyze_requirements",
                next_step=definition.steps[1],
                outputs={},
            )
            # last_event_seq is now 6; completing would append seq=7.
            # Pre-insert a seq=7 event so the repository's own
            # workflow.completed insert collides, forcing that
            # statement to fail after the guarded UPDATE already
            # matched a row.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_events "
                        "(event_id, workflow_id, seq, event_type, schema_version, "
                        " payload, occurred_at) "
                        "VALUES ('evt_preexisting', :workflow_id, 7, 'manual.duplicate', 1, "
                        " '{}'::jsonb, now())"
                    ),
                    {"workflow_id": created.workflow_id},
                )

            with pytest.raises(WorkflowInstanceCreationError):
                await repository.advance_workflow(
                    workflow_id=created.workflow_id,
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    expected_current_step_id="implement",
                    next_step=None,
                    outputs={},
                )

            stored = await _fetch_instance(database_url, created.workflow_id)
            assert stored is not None
            assert stored["status"] == "running"
            assert stored["completed_at"] is None
            assert stored["last_event_seq"] == 6

            # The two executed steps' rows are untouched by the rejected
            # completion attempt; no workflow_steps row is ever written
            # for the completion branch itself (next_step=None).
            steps = await _fetch_workflow_steps(database_url, created.workflow_id)
            assert len(steps) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())
