"""Unit tests for QualityGateStepExecutor's own evaluation logic — a
fake repository throughout, isolating "does the gate correctly read a
source step's real output and decide pass/fail" from any real
database (ADR-0004: interface-driven, so a fake Protocol implementation
is a legitimate substitute in a unit test). The end-to-end proof that
this genuinely halts `se.delivery_pipeline` lives in
`tests/integration/workflow_engine/test_delivery_pipeline.py`."""

from datetime import UTC, datetime
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.quality_gate import QualityGateStepExecutor
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_GATE_STEP = WorkflowStep(id="quality-gate-tests-pass", type=StepType.QUALITY_GATE)


def _step_record(
    *, step_name: str, outputs: dict[str, Any] | None, attempt: int = 1
) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id=f"step_{step_name}_{attempt}",
        workflow_id="wf_fake",
        step_name=step_name,
        step_type=StepType.AGENT,
        status="completed" if outputs is not None else "started",
        attempt=attempt,
        agent_id="pack/agent",
        tool_id=None,
        prompt_id=None,
        prompt_version=None,
        model_alias=None,
        inputs={},
        outputs=outputs,
        error=None,
        idempotency_key=f"key_{step_name}_{attempt}",
        usage={},
        started_at=now,
        completed_at=now if outputs is not None else None,
    )


class _FakeRepository:
    """Returns a fixed, pre-seeded list of step records; every other
    Protocol method is unused by this executor and raises if called."""

    def __init__(self, steps: list[WorkflowStepRecord]) -> None:
        self._steps = steps

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        return self._steps

    async def create(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def transition_to_running(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        raise NotImplementedError("not exercised by these tests")

    async def advance_workflow(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def reset_current_step(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


@pytest.mark.asyncio
async def test_a_passing_source_step_lets_the_gate_pass() -> None:
    repository = _FakeRepository([_step_record(step_name="test", outputs={"passed": True})])
    executor = QualityGateStepExecutor(repository, gate_sources={"quality-gate-tests-pass": "test"})

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {"gateId": "quality-gate-tests-pass", "sourceStepId": "test", "passed": True}


@pytest.mark.asyncio
async def test_a_failing_source_step_blocks_the_gate() -> None:
    repository = _FakeRepository(
        [_step_record(step_name="test", outputs={"passed": False, "exitCode": 1})]
    )
    executor = QualityGateStepExecutor(repository, gate_sources={"quality-gate-tests-pass": "test"})

    with pytest.raises(QualityGateFailedError, match="quality-gate-tests-pass"):
        await executor.execute(_GATE_STEP, workflow_id="wf_fake")


@pytest.mark.asyncio
async def test_a_source_step_with_no_persisted_output_yet_blocks_the_gate() -> None:
    repository = _FakeRepository([_step_record(step_name="test", outputs=None)])
    executor = QualityGateStepExecutor(repository, gate_sources={"quality-gate-tests-pass": "test"})

    with pytest.raises(QualityGateFailedError, match="no persisted output"):
        await executor.execute(_GATE_STEP, workflow_id="wf_fake")


@pytest.mark.asyncio
async def test_a_gate_step_absent_from_gate_sources_passes_with_empty_outputs() -> None:
    """The identical "an unconfigured step contributes/blocks nothing"
    shape `WorkflowStepOutputResolver` already established — a workflow
    may declare a quality_gate step this executor's own caller hasn't
    (yet) configured, without that step failing by default."""
    repository = _FakeRepository([])
    executor = QualityGateStepExecutor(repository, gate_sources={})

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {}


@pytest.mark.asyncio
async def test_the_highest_attempt_wins_when_a_source_step_has_more_than_one_row() -> None:
    repository = _FakeRepository(
        [
            _step_record(step_name="test", outputs={"passed": False}, attempt=1),
            _step_record(step_name="test", outputs={"passed": True}, attempt=2),
        ]
    )
    executor = QualityGateStepExecutor(repository, gate_sources={"quality-gate-tests-pass": "test"})

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs["passed"] is True


@pytest.mark.asyncio
async def test_a_custom_success_field_is_honoured_not_just_the_default_passed() -> None:
    repository = _FakeRepository([_step_record(step_name="scan", outputs={"clean": True})])
    executor = QualityGateStepExecutor(
        repository, gate_sources={"quality-gate-tests-pass": "scan"}, success_field="clean"
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {"gateId": "quality-gate-tests-pass", "sourceStepId": "scan", "clean": True}


@pytest.mark.asyncio
async def test_a_non_quality_gate_step_is_rejected() -> None:
    executor = QualityGateStepExecutor(_FakeRepository([]), gate_sources={})
    agent_step = WorkflowStep(id="build", type=StepType.AGENT, agent_id="pack/build")

    with pytest.raises(ValueError, match="only handles quality_gate steps"):
        await executor.execute(agent_step, workflow_id="wf_fake")


@pytest.mark.asyncio
async def test_a_missing_workflow_id_is_rejected_for_a_configured_gate() -> None:
    executor = QualityGateStepExecutor(
        _FakeRepository([]), gate_sources={"quality-gate-tests-pass": "test"}
    )

    with pytest.raises(ValueError, match="requires a real workflow_id"):
        await executor.execute(_GATE_STEP)
