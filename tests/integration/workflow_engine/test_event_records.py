"""WorkflowInstanceRepository.list_events against a real Postgres
container (ADR-0015 — no mocking the database). Proves: the append-only
event log (data_model.md §4.2) is readable back through the repository
interface, in seq order, and that an instance with no events yet (or an
unknown workflow_id) returns an empty list rather than an error.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
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
            "failureHandling": {"onError": "escalate"},
        }
    )


def test_list_events_returns_the_full_log_in_seq_order(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            service = WorkflowInstanceService(
                repository, NoOpStepExecutor(), SqlWorkflowDefinitionCatalog(engine)
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
            await service.advance(workflow_id=created.workflow_id, definition=definition)

            events = await repository.list_events(created.workflow_id)

            assert all(isinstance(event, WorkflowEventRecord) for event in events)
            assert [event.workflow_id for event in events] == [created.workflow_id] * 7
            assert [event.seq for event in events] == [1, 2, 3, 4, 5, 6, 7]
            assert [event.event_type for event in events] == [
                "workflow.started",
                "state.transitioned",
                "step.started",
                "step.completed",
                "step.started",
                "step.completed",
                "workflow.completed",
            ]
            assert events[0].step_id is None
            assert events[1].step_id is None
            assert events[2].step_id == "analyze_requirements"
            assert events[3].step_id == "analyze_requirements"
            assert events[4].step_id == "implement"
            assert events[5].step_id == "implement"
            assert events[6].step_id is None
            assert events[6].payload == {}
            for event in events:
                assert event.schema_version == 1
                assert event.agent_id is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_events_reflects_only_workflow_started_right_after_creation(
    database_url: str,
) -> None:
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

            events = await repository.list_events(created.workflow_id)

            assert [event.event_type for event in events] == ["workflow.started"]
            assert events[0].seq == 1
            assert events[0].payload["definitionId"] == _DEFINITION_ID

            # An unknown workflow_id is not an error either — an empty
            # log, same reasoning as list_steps().
            assert await repository.list_events("wf_does_not_exist") == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
