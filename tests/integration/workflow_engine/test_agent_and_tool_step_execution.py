"""Real (trivial) agent and tool invocation wired into step progression,
against a real Postgres container (ADR-0015 — no mocking the database).
Proves an Agent-type step's output actually comes from the agent, a
Tool-type step's output actually comes from the tool, and a step of
neither type still goes through the no-op path — end to end through
`WorkflowInstanceService.advance`.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)
from ai_os_kernel.workflow_engine.tool import EchoTool
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_AGENT_ID = "se.software_engineering/analyst"
_TOOL_ID = "se.build"


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


def _definition_with_an_agent_step_a_tool_step_and_a_human_approval_step() -> WorkflowDefinition:
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
                {"id": "analyze_requirements", "type": "agent", "agentId": _AGENT_ID},
                {"id": "run_build", "type": "tool", "toolId": _TOOL_ID},
                {"id": "release_approval", "type": "human_approval"},
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


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


def test_agent_and_tool_steps_produce_real_output_while_other_steps_stay_a_noop(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            step_executor = DispatchingStepExecutor(
                agent_executor=AgentStepExecutor(InMemoryAgentRegistry({_AGENT_ID: EchoAgent()})),
                tool_executor=ToolStepExecutor(InMemoryToolRegistry({_TOOL_ID: EchoTool()})),
                default_executor=NoOpStepExecutor(),
            )
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                step_executor,
                SqlWorkflowDefinitionCatalog(engine),
            )
            definition = _definition_with_an_agent_step_a_tool_step_and_a_human_approval_step()

            created = await service.create_instance(
                definition=definition,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
                pack_id="se.software_engineering",
            )
            await service.start(workflow_id=created.workflow_id, reason="worker picked it up")

            after_agent_step = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_agent_step.current_step_id == "analyze_requirements"

            after_tool_step = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_tool_step.current_step_id == "run_build"

            after_other_step = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert after_other_step.current_step_id == "release_approval"

            completed = await service.advance(
                workflow_id=created.workflow_id, definition=definition
            )
            assert completed.status == WorkflowInstanceStatus.COMPLETED

            events = await _fetch_events(database_url, created.workflow_id)

            def _completed_outputs(step_id: str) -> dict[str, Any]:
                event = next(
                    e
                    for e in events
                    if e["event_type"] == "step.completed" and e["step_id"] == step_id
                )
                return cast(dict[str, Any], event["payload"]["outputs"])

            assert _completed_outputs("analyze_requirements") == {"status": "ok"}
            assert _completed_outputs("run_build") == {"result": "ok"}
            assert _completed_outputs("release_approval") == {}
        finally:
            await engine.dispose()

    asyncio.run(_run())
