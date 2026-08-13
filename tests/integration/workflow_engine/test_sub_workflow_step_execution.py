"""Real, genuine sub-workflow invocation/execution against a real
Postgres container (ADR-0015 — no mocking the database). Proves a
``sub_workflow`` step (:class:`~ai_os_kernel.workflow_engine.
step_executor.SubWorkflowStepExecutor`, ``P02-S01-M05-T11``) genuinely
creates a real, separate child ``WorkflowInstance``, runs it to
completion via a real, independent ``WorkflowInstanceService``/
``WorkflowAdvanceRunner`` pair, and joins on that child's own real,
persisted last-step output — not a stub, not the parent's own state
reused, and not merely returning a value nothing reads.
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
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import SubWorkflowFailedError
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    SubWorkflowStepExecutor,
    ToolStepExecutor,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PARENT_DEFINITION_ID = "se.parent_workflow"
_CHILD_DEFINITION_ID = "se.child_workflow"
_DEFINITION_VERSION = "1.0.0"
_AGENT_ID = "se.software_engineering/analyst"
_PACK_ID = "se.software_engineering"
_PRINCIPAL_ID = "user-42"


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
            "name": "Child Workflow",
            "description": "A real, separate child workflow a sub_workflow step invokes.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_the_work", "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


def _parent_definition(sub_workflow_id: str) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _PARENT_DEFINITION_ID,
            "name": "Parent Workflow",
            "description": "Invokes a child workflow via a sub_workflow step.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": "invoke_child", "type": "sub_workflow", "subWorkflowId": sub_workflow_id}
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


def _make_child_service(engine: AsyncEngine) -> WorkflowInstanceService:
    step_executor = DispatchingStepExecutor(
        agent_executor=AgentStepExecutor(InMemoryAgentRegistry({_AGENT_ID: EchoAgent()})),
        tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
        default_executor=NoOpStepExecutor(),
    )
    return WorkflowInstanceService(
        SqlWorkflowInstanceRepository(engine), step_executor, SqlWorkflowDefinitionCatalog(engine)
    )


def _make_parent_service(
    engine: AsyncEngine, *, definitions: dict[str, WorkflowDefinition]
) -> WorkflowInstanceService:
    """A genuinely separate ``WorkflowInstanceService``/
    ``WorkflowAdvanceRunner`` pair drives the child instance — real
    objects, the same classes any top-level caller already uses, not a
    fake or a shortcut through the parent's own state. Two distinct
    service objects (rather than one shared, self-referential instance)
    because ``DispatchingStepExecutor`` needs its own
    ``sub_workflow_executor`` at construction time, which itself needs
    a real ``instance_service`` to drive the child — a genuine
    composition-order dependency, not a design flaw; both objects share
    the identical real ``engine``/database, so the child instance they
    create is exactly as real as the parent's."""
    repository = SqlWorkflowInstanceRepository(engine)
    child_service = _make_child_service(engine)
    child_runner = WorkflowAdvanceRunner(
        child_service, WorkflowLeaseService(SqlWorkflowLeaseRepository(engine))
    )
    sub_workflow_executor = SubWorkflowStepExecutor(
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
        agent_executor=AgentStepExecutor(InMemoryAgentRegistry({})),
        tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
        default_executor=NoOpStepExecutor(),
        sub_workflow_executor=sub_workflow_executor,
    )
    return WorkflowInstanceService(repository, step_executor, SqlWorkflowDefinitionCatalog(engine))


def test_a_sub_workflow_step_genuinely_creates_and_completes_a_real_child_instance(
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

            after_sub_workflow_step = await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )
            assert after_sub_workflow_step.current_step_id == "invoke_child"

            completed = await parent_service.advance(
                workflow_id=created.workflow_id, definition=parent_definition
            )
            assert completed.status == WorkflowInstanceStatus.COMPLETED

            repository = SqlWorkflowInstanceRepository(engine)
            parent_steps = await repository.list_steps(created.workflow_id)
            sub_workflow_record = next(s for s in parent_steps if s.step_name == "invoke_child")
            assert sub_workflow_record.outputs is not None
            outputs: dict[str, Any] = sub_workflow_record.outputs
            child_workflow_id = outputs["childWorkflowId"]

            # The real proof: a genuinely separate child WorkflowInstance
            # exists, in COMPLETED status, distinct from the parent.
            assert child_workflow_id != created.workflow_id
            child_instance = await repository.get_instance(child_workflow_id)
            assert child_instance is not None
            assert child_instance.status == WorkflowInstanceStatus.COMPLETED
            assert child_instance.definition_id == _CHILD_DEFINITION_ID

            child_steps = await repository.list_steps(child_workflow_id)
            assert [s.step_name for s in child_steps] == ["do_the_work"]
            assert child_steps[0].outputs == {"status": "ok"}

            # The real join: the parent's own persisted step output
            # genuinely carries the child's own real, persisted
            # last-step output forward.
            assert outputs["subWorkflowId"] == _CHILD_DEFINITION_ID
            assert outputs["outputs"] == {"status": "ok"}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_sub_workflow_step_fails_clearly_when_its_declared_id_is_not_configured(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            parent_definition = _parent_definition("se.not_configured")
            parent_service = _make_parent_service(engine, definitions={})

            created = await parent_service.create_instance(
                definition=parent_definition,
                inputs={},
                principal_id=_PRINCIPAL_ID,
                pack_id=_PACK_ID,
            )
            await parent_service.start(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            with pytest.raises(SubWorkflowFailedError, match="se.not_configured"):
                await parent_service.advance(
                    workflow_id=created.workflow_id, definition=parent_definition
                )

            # A refused, unconfigured sub_workflow step leaves the
            # parent instance exactly where it started — never a
            # half-created child, never a silently skipped step.
            instance = await SqlWorkflowInstanceRepository(engine).get_instance(created.workflow_id)
            assert instance is not None
            assert instance.current_step_id is None
            assert instance.status == WorkflowInstanceStatus.RUNNING
        finally:
            await engine.dispose()

    asyncio.run(_run())
