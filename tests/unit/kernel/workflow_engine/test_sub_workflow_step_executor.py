"""Unit tests for ``SubWorkflowStepExecutor``'s own logic — fake
``instance_service``/``advance_runner``/``repository`` throughout,
isolating what this executor itself does (resolve, create, start, run,
join) from what a real ``WorkflowInstanceService``/
``WorkflowAdvanceRunner``/``WorkflowInstanceRepository`` do internally,
which is already proven, real, end to end, against a real Postgres
container by
``tests/integration/workflow_engine/test_sub_workflow_step_execution.py``
(``P02-S01-M05-T11``)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome, WorkflowRunResult
from ai_os_kernel.workflow_engine.errors import SubWorkflowFailedError
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.step_executor import SubWorkflowStepExecutor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_CHILD_DEFINITION_ID = "se.child_workflow"
_AGENT_ID = "se.software_engineering/analyst"
_PACK_ID = "se.software_engineering"
_PRINCIPAL_ID = "user-42"


def _child_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _CHILD_DEFINITION_ID,
            "name": "Child Workflow",
            "description": "test fixture",
            "version": "1.0.0",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_the_work", "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


def _sub_workflow_step() -> WorkflowStep:
    return WorkflowStep.model_validate(
        {"id": "invoke_child", "type": "sub_workflow", "subWorkflowId": _CHILD_DEFINITION_ID}
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


def _step_record(*, step_name: str, outputs: dict[str, Any] | None) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id="stp_fake",
        workflow_id="wf_child",
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
        idempotency_key="wf_child:do_the_work:1",
        usage={},
        started_at=now,
        completed_at=now,
    )


class _FakeInstanceService:
    """Records every call; returns a canned, real-shaped
    ``WorkflowInstance`` — never touches a database."""

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
            workflow_id="wf_child", status=WorkflowInstanceStatus.CREATED, current_step_id=None
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
    whichever outcome the test configures — never touches a database."""

    def __init__(self, outcome: WorkflowRunOutcome) -> None:
        self._outcome = outcome
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
        final_status = (
            WorkflowInstanceStatus.COMPLETED
            if self._outcome is WorkflowRunOutcome.COMPLETED
            else WorkflowInstanceStatus.FAILED
        )
        return WorkflowRunResult(
            workflow_id=workflow_id,
            outcome=self._outcome,
            iterations=1,
            last_instance=_instance(
                workflow_id=workflow_id, status=final_status, current_step_id="do_the_work"
            ),
        )


class _FakeRepository:
    """A plain, canned read — never touches a database."""

    def __init__(
        self, *, instance: WorkflowInstance | None, steps: list[WorkflowStepRecord]
    ) -> None:
        self._instance = instance
        self._steps = steps

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return self._instance

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        return self._steps


def _executor(
    *,
    definitions: dict[str, WorkflowDefinition],
    instance_service: _FakeInstanceService,
    advance_runner: _FakeAdvanceRunner,
    repository: _FakeRepository,
) -> SubWorkflowStepExecutor:
    return SubWorkflowStepExecutor(
        definitions=definitions,
        instance_service=instance_service,  # type: ignore[arg-type]
        advance_runner=advance_runner,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        pack_id=_PACK_ID,
        principal_id=_PRINCIPAL_ID,
        lease_duration_seconds=60,
        max_iterations=10,
    )


async def test_it_creates_starts_and_runs_a_real_child_and_joins_its_output() -> None:
    child_definition = _child_definition()
    instance_service = _FakeInstanceService()
    advance_runner = _FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED)
    repository = _FakeRepository(
        instance=_instance(
            workflow_id="wf_child",
            status=WorkflowInstanceStatus.COMPLETED,
            current_step_id="do_the_work",
        ),
        steps=[_step_record(step_name="do_the_work", outputs={"status": "ok"})],
    )
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: child_definition},
        instance_service=instance_service,
        advance_runner=advance_runner,
        repository=repository,
    )

    result = await executor.execute(_sub_workflow_step(), workflow_id="wf_parent")

    assert result == {
        "childWorkflowId": "wf_child",
        "subWorkflowId": _CHILD_DEFINITION_ID,
        "outputs": {"status": "ok"},
    }
    assert instance_service.create_calls == [
        {
            "definition": child_definition,
            "inputs": {},
            "principal_id": _PRINCIPAL_ID,
            "pack_id": _PACK_ID,
            "principal_permissions": None,
        }
    ]
    assert instance_service.start_calls[0]["workflow_id"] == "wf_child"
    assert advance_runner.run_calls[0]["workflow_id"] == "wf_child"
    assert advance_runner.run_calls[0]["definition"] == child_definition
    assert advance_runner.run_calls[0]["lease_duration_seconds"] == 60
    assert advance_runner.run_calls[0]["max_iterations"] == 10


async def test_it_fails_clearly_when_the_declared_sub_workflow_id_is_not_configured() -> None:
    executor = _executor(
        definitions={},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(instance=None, steps=[]),
    )

    with pytest.raises(SubWorkflowFailedError, match=_CHILD_DEFINITION_ID):
        await executor.execute(_sub_workflow_step())


async def test_it_fails_clearly_when_the_child_does_not_reach_completed() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.FAILED),
        repository=_FakeRepository(instance=None, steps=[]),
    )

    with pytest.raises(SubWorkflowFailedError, match="did not complete"):
        await executor.execute(_sub_workflow_step())


async def test_it_refuses_a_step_of_any_other_type() -> None:
    executor = _executor(
        definitions={_CHILD_DEFINITION_ID: _child_definition()},
        instance_service=_FakeInstanceService(),
        advance_runner=_FakeAdvanceRunner(WorkflowRunOutcome.COMPLETED),
        repository=_FakeRepository(instance=None, steps=[]),
    )
    not_sub_workflow = WorkflowStep(id="analyze", type=StepType.AGENT, agent_id=_AGENT_ID)

    with pytest.raises(ValueError, match="only handles sub_workflow steps"):
        await executor.execute(not_sub_workflow)
