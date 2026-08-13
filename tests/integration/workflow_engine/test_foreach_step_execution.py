"""Real, genuine ``foreach`` fan-out against a real Postgres container
(ADR-0015 — no mocking the database). Proves a ``foreach`` step
(:class:`~ai_os_kernel.workflow_engine.step_executor.ForeachStepExecutor`,
`P08-S02-M30-T01`, ADR-0021) genuinely reads a named prior step's own
real, persisted list output, creates one real, separate child
``WorkflowInstance`` per real item, runs each to completion via a real,
independent ``WorkflowInstanceService``/``WorkflowAdvanceRunner`` pair,
and joins on each child's own real, persisted last-step output — not a
stub, not the parent's own state reused, and not merely returning a
value nothing reads.

Mirrors ``test_sub_workflow_step_execution.py``'s own structure exactly
— the same real-Postgres, two-independent-service-pair shape,
``ForeachStepExecutor`` reuses per item rather than inventing a second
one.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import ForeachFailedError
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    ForeachStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PARENT_DEFINITION_ID = "se.parent_workflow_foreach"
_CHILD_DEFINITION_ID = "se.implement_task"
_DEFINITION_VERSION = "1.0.0"
_PLANNER_AGENT_ID = "se.software_engineering/planner"
_WORKER_AGENT_ID = "se.software_engineering/worker"
_PACK_ID = "se.software_engineering"
_PRINCIPAL_ID = "user-42"


class _PlanProducingAgent:
    """A real, deterministic in-process agent (the same
    ``execute(inputs) -> outputs`` Protocol
    :class:`~ai_os_kernel.workflow_engine.agent.EchoAgent` already
    establishes) whose output genuinely includes a ``tasks`` list — the
    real "plan artifact" shape a ``foreach`` step's own
    ``sourceStepId``/``itemsField`` reads, standing in for
    ``technical-planner``'s own real ``implementation_plan.tasks``
    output without needing a live LLM credential."""

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            }
        },
        "required": ["tasks"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"tasks": [{"title": "task-one"}, {"title": "task-two"}]}


class _WorkerAgent:
    """The real per-child agent. A fixed output (the identical
    ``EchoAgent`` shape ``test_sub_workflow_step_execution.py`` already
    uses) is enough here: ``AgentStepExecutor`` never forwards a step's
    ``WorkflowInstance.inputs`` into an agent's own invocation ``inputs``
    (only ``stepId``/``agentId``/``workflowId``/prompt fields, plus an
    assembled ``context`` key when a real ``ContextManager`` is wired —
    see that executor's own docstring). Distinguishing which real child
    ran which real fanned-out item is instead proven directly against
    each child's own real, persisted ``WorkflowInstance.inputs``, not
    through this agent's output."""

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"status": {"const": "ok"}},
        "required": ["status"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}


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


def _child_definition(definition_id: str = _CHILD_DEFINITION_ID) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": definition_id,
            "name": "Implement One Task",
            "description": "A real, separate child workflow a foreach step invokes per item.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_the_work", "type": "agent", "agentId": _WORKER_AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


def _parent_definition(sub_workflow_id: str, *, max_fan_out: int = 5) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _PARENT_DEFINITION_ID,
            "name": "Parent Workflow",
            "description": "Produces a plan, then fans out over it via a foreach step.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": "produce_plan", "type": "agent", "agentId": _PLANNER_AGENT_ID},
                {
                    "id": "implement_tasks",
                    "type": "foreach",
                    "subWorkflowId": sub_workflow_id,
                    "foreach": {
                        "sourceStepId": "produce_plan",
                        "itemsField": "tasks",
                        "maxFanOut": max_fan_out,
                    },
                },
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


def _make_child_service(engine: AsyncEngine) -> WorkflowInstanceService:
    step_executor = DispatchingStepExecutor(
        agent_executor=AgentStepExecutor(InMemoryAgentRegistry({_WORKER_AGENT_ID: _WorkerAgent()})),
        tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
        default_executor=NoOpStepExecutor(),
    )
    return WorkflowInstanceService(
        SqlWorkflowInstanceRepository(engine), step_executor, SqlWorkflowDefinitionCatalog(engine)
    )


def _make_parent_service(
    engine: AsyncEngine, *, definitions: dict[str, WorkflowDefinition]
) -> WorkflowInstanceService:
    """Two genuinely separate ``WorkflowInstanceService``/
    ``WorkflowAdvanceRunner`` pairs — the identical composition-order
    reasoning ``test_sub_workflow_step_execution.py``'s own
    ``_make_parent_service`` already documents: ``DispatchingStepExecutor``
    needs its own ``foreach_executor`` at construction time, which
    itself needs a real ``instance_service`` to drive each child. Both
    pairs share the identical real ``engine``/database, so every child
    instance created is exactly as real as the parent's."""
    repository = SqlWorkflowInstanceRepository(engine)
    child_service = _make_child_service(engine)
    child_runner = WorkflowAdvanceRunner(
        child_service, WorkflowLeaseService(SqlWorkflowLeaseRepository(engine))
    )
    foreach_executor = ForeachStepExecutor(
        definitions=definitions,
        instance_service=child_service,
        advance_runner=child_runner,
        repository=repository,
        pack_id=_PACK_ID,
        principal_id=_PRINCIPAL_ID,
        lease_duration_seconds=60,
        max_iterations=10,
    )
    step_executor = DispatchingStepExecutor(
        agent_executor=AgentStepExecutor(
            InMemoryAgentRegistry({_PLANNER_AGENT_ID: _PlanProducingAgent()})
        ),
        tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
        default_executor=NoOpStepExecutor(),
        foreach_executor=foreach_executor,
    )
    return WorkflowInstanceService(repository, step_executor, SqlWorkflowDefinitionCatalog(engine))


def test_a_foreach_step_genuinely_fans_out_one_real_child_per_real_item(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            child_definition = _child_definition()
            parent_definition = _parent_definition(child_definition.id)
            parent_service = _make_parent_service(
                engine, definitions={child_definition.id: child_definition}
            )

            created = await parent_service.create_instance(
                definition=parent_definition,
                inputs={},
                principal_id=_PRINCIPAL_ID,
                pack_id=_PACK_ID,
            )
            await parent_service.start(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            after_plan_step = await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )
            assert after_plan_step.current_step_id == "produce_plan"

            after_foreach_step = await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )
            assert after_foreach_step.current_step_id == "implement_tasks"
            assert after_foreach_step.status == WorkflowInstanceStatus.RUNNING

            completed = await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )
            assert completed.status == WorkflowInstanceStatus.COMPLETED
            assert completed.current_step_id == "implement_tasks"

            repository = SqlWorkflowInstanceRepository(engine)
            parent_steps = await repository.list_steps(created.workflow_id)
            foreach_record = next(s for s in parent_steps if s.step_name == "implement_tasks")
            assert foreach_record.outputs is not None
            outputs: dict[str, Any] = foreach_record.outputs

            assert outputs["subWorkflowId"] == _CHILD_DEFINITION_ID
            assert outputs["itemCount"] == 2
            assert len(outputs["results"]) == 2

            # The real proof: two genuinely separate child
            # WorkflowInstances exist, each in COMPLETED status, each
            # distinct from the parent and from each other, each
            # created with the exact real item it was fanned out with
            # as its own persisted `inputs`, and each one's own real
            # persisted step output is what the parent's own foreach
            # step record joined forward.
            fanned_out_titles: set[str] = set()
            child_workflow_ids: set[str] = set()
            for item_result in outputs["results"]:
                child_workflow_id = item_result["childWorkflowId"]
                assert child_workflow_id != created.workflow_id
                child_workflow_ids.add(child_workflow_id)

                child_instance = await repository.get_instance(child_workflow_id)
                assert child_instance is not None
                assert child_instance.status == WorkflowInstanceStatus.COMPLETED
                assert child_instance.definition_id == _CHILD_DEFINITION_ID
                fanned_out_titles.add(child_instance.inputs["title"])

                child_steps = await repository.list_steps(child_workflow_id)
                assert [s.step_name for s in child_steps] == ["do_the_work"]
                assert item_result["outputs"] == child_steps[0].outputs
                assert item_result["outputs"] == {"status": "ok"}

            assert len(child_workflow_ids) == 2
            assert fanned_out_titles == {"task-one", "task-two"}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_foreach_step_fails_clearly_when_item_count_exceeds_max_fan_out(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            child_definition = _child_definition()
            parent_definition = _parent_definition(child_definition.id, max_fan_out=1)
            parent_service = _make_parent_service(
                engine, definitions={child_definition.id: child_definition}
            )

            created = await parent_service.create_instance(
                definition=parent_definition,
                inputs={},
                principal_id=_PRINCIPAL_ID,
                pack_id=_PACK_ID,
            )
            await parent_service.start(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )

            with pytest.raises(ForeachFailedError, match="exceeds the declared maxFanOut"):
                await parent_service.advance(
                    workflow_id=created.workflow_id, definition=parent_definition
                )

            # A refused, over-bound foreach step leaves the parent
            # instance exactly where it started — never a
            # partially-fanned-out set of children.
            instance = await SqlWorkflowInstanceRepository(engine).get_instance(created.workflow_id)
            assert instance is not None
            assert instance.current_step_id == "produce_plan"
            assert instance.status == WorkflowInstanceStatus.RUNNING
        finally:
            await engine.dispose()

    asyncio.run(_run())
