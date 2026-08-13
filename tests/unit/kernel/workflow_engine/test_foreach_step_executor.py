"""Unit tests for ``ForeachStepExecutor``'s own logic — fake
``instance_service``/``advance_runner``/``repository`` throughout, the
identical isolation shape
``tests/unit/kernel/workflow_engine/test_sub_workflow_step_executor.py``
already establishes for ``SubWorkflowStepExecutor``, the mechanism this
executor reuses per item. Real, Postgres-backed, genuine multi-child
fan-out is proven separately by
``tests/integration/workflow_engine/test_foreach_step_execution.py``."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome, WorkflowRunResult
from ai_os_kernel.workflow_engine.errors import ForeachFailedError
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.step_executor import ForeachStepExecutor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_CHILD_DEFINITION_ID = "se.implement_task"
_AGENT_ID = "se.software_engineering/analyst"
_PACK_ID = "se.software_engineering"
_PRINCIPAL_ID = "user-42"
_PARENT_WORKFLOW_ID = "wf_parent"
_SOURCE_STEP_ID = "technical-planner"


def _child_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _CHILD_DEFINITION_ID,
            "name": "Implement One Task",
            "description": "test fixture",
            "version": "1.0.0",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_the_work", "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


def _foreach_step(*, max_fan_out: int = 5) -> WorkflowStep:
    return WorkflowStep.model_validate(
        {
            "id": "implement_tasks",
            "type": "foreach",
            "subWorkflowId": _CHILD_DEFINITION_ID,
            "foreach": {
                "sourceStepId": _SOURCE_STEP_ID,
                "itemsField": "tasks",
                "maxFanOut": max_fan_out,
            },
        }
    )


def _instance(
    *, workflow_id: str, status: WorkflowInstanceStatus, current_step_id: str | None
) -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id=workflow_id,
        definition_id=_CHILD_DEFINITION_ID,
        definition_version="1.0.0",
        status=status,
        current_step_id=current_step_id,
        inputs={},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id=_PRINCIPAL_ID,
        principal_permissions=None,
        scheduled_at=None,
        last_event_seq=1,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def _step_record(
    *, workflow_id: str, step_name: str, outputs: dict[str, Any] | None
) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id=f"stp_{workflow_id}_{step_name}",
        workflow_id=workflow_id,
        step_name=step_name,
        step_type=StepType.AGENT,
        status="completed",
        attempt=1,
        agent_id=_AGENT_ID,
        tool_id=None,
        prompt_id=None,
        prompt_version=None,
        model_alias=None,
        inputs={},
        outputs=outputs,
        error=None,
        idempotency_key=f"{workflow_id}:{step_name}:1",
        usage={},
        started_at=now,
        completed_at=now,
    )


class _FakeInstanceService:
    """Records every call; returns a canned, real-shaped
    ``WorkflowInstance`` per call — never touches a database. Child
    workflow ids are assigned sequentially (``wf_child_0``,
    ``wf_child_1``, ...) so a test can tell fan-out items apart."""

    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.start_calls: list[dict[str, Any]] = []

    async def create_instance(
        self,
        *,
        definition: WorkflowDefinition,
        inputs: dict[str, Any],
        principal_id: str,
        pack_id: str,
        principal_permissions: frozenset[str] | None = None,
    ) -> WorkflowInstance:
        child_workflow_id = f"wf_child_{len(self.create_calls)}"
        self.create_calls.append(
            {
                "definition": definition,
                "inputs": inputs,
                "principal_id": principal_id,
                "pack_id": pack_id,
                "principal_permissions": principal_permissions,
            }
        )
        return _instance(
            workflow_id=child_workflow_id,
            status=WorkflowInstanceStatus.CREATED,
            current_step_id=None,
        )

    async def start(
        self, *, workflow_id: str, reason: str, triggering_event_id: str | None = None
    ) -> WorkflowInstance:
        self.start_calls.append({"workflow_id": workflow_id, "reason": reason})
        return _instance(
            workflow_id=workflow_id, status=WorkflowInstanceStatus.RUNNING, current_step_id=None
        )


class _FakeAdvanceRunner:
    """Records every call; returns a canned ``WorkflowRunResult`` for
    whichever outcome the test configures — never touches a database.
    A per-child override lets a test fail exactly one item in a
    multi-item fan-out."""

    def __init__(
        self,
        outcome: WorkflowRunOutcome,
        *,
        outcome_overrides: dict[str, WorkflowRunOutcome] | None = None,
    ) -> None:
        self._outcome = outcome
        self._outcome_overrides = outcome_overrides or {}
        self.run_calls: list[dict[str, Any]] = []

    async def run_to_completion(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        worker_id: str,
        lease_duration_seconds: int,
        max_iterations: int,
        step_retry_targets: Any = None,
    ) -> WorkflowRunResult:
        self.run_calls.append(
            {
                "workflow_id": workflow_id,
                "definition": definition,
                "worker_id": worker_id,
                "lease_duration_seconds": lease_duration_seconds,
                "max_iterations": max_iterations,
            }
        )
        outcome = self._outcome_overrides.get(workflow_id, self._outcome)
        final_status = (
            WorkflowInstanceStatus.COMPLETED
            if outcome is WorkflowRunOutcome.COMPLETED
            else WorkflowInstanceStatus.FAILED
        )
        return WorkflowRunResult(
            workflow_id=workflow_id,
            outcome=outcome,
            iterations=1,
            last_instance=_instance(
                workflow_id=workflow_id, status=final_status, current_step_id="do_the_work"
            ),
        )


class _FakeRepository:
    """A plain, canned read — never touches a database.
    ``parent_steps`` answers the parent workflow's own
    ``list_steps`` (the source-step-output lookup);
    ``child_outputs`` answers each real child workflow id's own
    ``do_the_work`` output for the post-completion join."""

    def __init__(
        self,
        *,
        parent_steps: list[WorkflowStepRecord],
        child_outputs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._parent_steps = parent_steps
        self._child_outputs = child_outputs or {}

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        if workflow_id not in self._child_outputs:
            return None
        return _instance(
            workflow_id=workflow_id,
            status=WorkflowInstanceStatus.COMPLETED,
            current_step_id="do_the_work",
        )

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        if workflow_id == _PARENT_WORKFLOW_ID:
            return self._parent_steps
        outputs = self._child_outputs.get(workflow_id)
        if outputs is None:
            return []
        return [_step_record(workflow_id=workflow_id, step_name="do_the_work", outputs=outputs)]


def _executor(
    *,
    definitions: dict[str, WorkflowDefinition],
    instance_service: _FakeInstanceService,
    advance_runner: _FakeAdvanceRunner,
    repository: _FakeRepository,
) -> ForeachStepExecutor:
    return ForeachStepExecutor(
        definitions=definitions,
        instance_service=instance_service,  # type: ignore[arg-type]
        advance_runner=advance_runner,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        pack_id=_PACK_ID,
        principal_id=_PRINCIPAL_ID,
        lease_duration_seconds=60,
        max_iterations=10,
    )


def _source_output_steps(*, tasks: Any) -> list[WorkflowStepRecord]:
    return [
        _step_record(
            workflow_id=_PARENT_WORKFLOW_ID,
            step_name=_SOURCE_STEP_ID,
            outputs={"tasks": tasks},
        )
    ]


async def test_it_creates_starts_and_runs_one_real_child_per_item_and_joins_outputs() -> None:
    child_definition = _child_definition()
    instance_service = _FakeInstanceService()
    advance_runner = _FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED)
    repository = _FakeRepository(
        parent_steps=_source_output_steps(tasks=[{"title": "task-a"}, {"title": "task-b"}]),
        child_outputs={
            "wf_child_0": {"status": "ok-a"},
            "wf_child_1": {"status": "ok-b"},
        },
    )
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: child_definition},
        instance_service=instance_service,
        advance_runner=advance_runner,
        repository=repository,
    )

    result = await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)

    assert result == {
        "subWorkflowId": _CHILD_DEFINITION_ID,
        "itemCount": 2,
        "results": [
            {"childWorkflowId": "wf_child_0", "outputs": {"status": "ok-a"}},
            {"childWorkflowId": "wf_child_1", "outputs": {"status": "ok-b"}},
        ],
    }
    assert [call["inputs"] for call in instance_service.create_calls] == [
        {"title": "task-a"},
        {"title": "task-b"},
    ]
    assert [call["workflow_id"] for call in instance_service.start_calls] == [
        "wf_child_0",
        "wf_child_1",
    ]
    assert [call["workflow_id"] for call in advance_runner.run_calls] == [
        "wf_child_0",
        "wf_child_1",
    ]


async def test_it_fails_clearly_when_item_count_exceeds_max_fan_out() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(
            parent_steps=_source_output_steps(tasks=[{"title": "a"}, {"title": "b"}]),
        ),
    )

    with pytest.raises(ForeachFailedError, match="exceeds the declared maxFanOut"):
        await executor.execute(_foreach_step(max_fan_out=1), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_the_source_step_has_no_output_yet() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=[]),
    )

    with pytest.raises(ForeachFailedError, match="no persisted output yet"):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_the_items_field_is_missing() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(
            parent_steps=[
                _step_record(
                    workflow_id=_PARENT_WORKFLOW_ID,
                    step_name=_SOURCE_STEP_ID,
                    outputs={"content": "no tasks field here"},
                )
            ]
        ),
    )

    with pytest.raises(ForeachFailedError, match="has no field 'tasks'"):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_the_items_field_is_not_a_list() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=_source_output_steps(tasks="not-a-list")),
    )

    with pytest.raises(ForeachFailedError, match="is not a real list"):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_one_item_is_not_a_json_object() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=_source_output_steps(tasks=["not-a-dict"])),
    )

    with pytest.raises(ForeachFailedError, match="is not a real JSON object"):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_the_declared_sub_workflow_id_is_not_configured() -> None:
    executor = _executor(
        definitions={},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=_source_output_steps(tasks=[{"title": "a"}])),
    )

    with pytest.raises(ForeachFailedError, match=_CHILD_DEFINITION_ID):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_fails_clearly_when_one_child_does_not_reach_completed() -> None:
    instance_service = _FakeInstanceService()
    advance_runner = _FakeAdvanceRunner(
        WorkflowRunOutcome.COMPLETED,
        outcome_overrides={"wf_child_1": WorkflowRunOutcome.FAILED},
    )
    repository = _FakeRepository(
        parent_steps=_source_output_steps(tasks=[{"title": "a"}, {"title": "b"}]),
        child_outputs={"wf_child_0": {"status": "ok"}},
    )
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=instance_service,
        advance_runner=advance_runner,
        repository=repository,
    )

    with pytest.raises(ForeachFailedError, match="did not complete"):
        await executor.execute(_foreach_step(), workflow_id=_PARENT_WORKFLOW_ID)


async def test_it_requires_a_real_workflow_id() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=[]),
    )

    with pytest.raises(ValueError, match="requires a real workflow_id"):
        await executor.execute(_foreach_step())


async def test_it_refuses_a_step_of_any_other_type() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(parent_steps=[]),
    )
    not_foreach = WorkflowStep(id="analyze", type=StepType.AGENT, agent_id=_AGENT_ID)

    with pytest.raises(ValueError, match="only handles foreach steps"):
        await executor.execute(not_foreach, workflow_id=_PARENT_WORKFLOW_ID)
