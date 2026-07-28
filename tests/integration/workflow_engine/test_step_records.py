"""WorkflowInstanceRepository.list_steps against a real Postgres
container (ADR-0015 — no mocking the database). Proves: the materialised
per-step history written by advance() (data_model.md §4.3) is readable
back through the repository interface, in execution order, and that an
instance with no executed steps yet returns an empty list rather than
an error.
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
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord
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
                    "promptId": "prompt_analyze_requirements",
                    "promptVersion": "1.0.0",
                    "modelAlias": "fast-cheap",
                },
                {"id": "implement", "type": "agent", "agentId": "se.software_engineering/analyst"},
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


def test_list_steps_returns_the_materialised_records_in_execution_order(
    database_url: str,
) -> None:
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
            # Completion (next_step=None) writes no workflow_steps row.
            await service.advance(workflow_id=created.workflow_id, definition=definition)

            steps = await repository.list_steps(created.workflow_id)

            assert [type(step) for step in steps] == [WorkflowStepRecord, WorkflowStepRecord]
            assert [step.step_name for step in steps] == ["analyze_requirements", "implement"]
            for step in steps:
                assert step.workflow_id == created.workflow_id
                assert step.step_type == StepType.AGENT
                assert step.status == "completed"
                assert step.attempt == 1
                assert step.agent_id == "se.software_engineering/analyst"
                assert step.tool_id is None
                assert step.inputs == {}
                assert step.outputs == {}
                assert step.error is None
                assert step.usage == {}
                assert step.completed_at is not None
                assert step.completed_at >= step.started_at
            # analyze_requirements declares promptId/promptVersion/modelAlias;
            # implement declares none of the three — both are recorded
            # faithfully, not silently coerced to a shared default.
            assert steps[0].prompt_id == "prompt_analyze_requirements"
            assert steps[0].prompt_version == "1.0.0"
            assert steps[0].model_alias == "fast-cheap"
            assert steps[1].prompt_id is None
            assert steps[1].prompt_version is None
            assert steps[1].model_alias is None
            assert steps[0].idempotency_key == f"{created.workflow_id}:analyze_requirements:1"
            assert steps[1].idempotency_key == f"{created.workflow_id}:implement:1"
            assert steps[0].started_at <= steps[1].started_at
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_steps_is_empty_before_any_step_has_executed(database_url: str) -> None:
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
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            assert await repository.list_steps(created.workflow_id) == []

            # An unknown workflow_id is not an error either — an empty
            # history, same as a real instance with no steps executed
            # yet. Existence checks belong to whichever caller cares.
            assert await repository.list_steps("wf_does_not_exist") == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
