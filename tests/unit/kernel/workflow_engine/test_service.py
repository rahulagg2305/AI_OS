"""Unit tests for WorkflowInstanceService: validate-then-delegate, with a
fake repository and a fake step executor — no database (ADR-0004:
interface-driven, so fake Protocol implementations are legitimate
substitutes in a unit test)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.errors import (
    DecisionConditionError,
    QualityGateFailedError,
    WorkflowInvalidTransitionError,
)
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    DecisionStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
)
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_DEFINITION_RAW: dict[str, Any] = {
    "id": "se.product_creation",
    "name": "Full Product Creation",
    "description": "Turn a structured specification into working software.",
    "version": "1.0.0",
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

_DEFINITION = WorkflowDefinition.model_validate(_DEFINITION_RAW)

_GATE_DEFINITION = WorkflowDefinition.model_validate(
    {
        "id": "se.gated_pipeline",
        "name": "Gated Pipeline",
        "description": "One agent step, then one real, blocking quality gate.",
        "version": "1.2.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [
            {"id": "build", "type": "agent", "agentId": "se.software_engineering/build"},
            {"id": "gate", "type": "quality_gate"},
        ],
        "failureHandling": {"onError": "halt"},
    }
)

# Deliberately adversarial to a positional-only resolver: "rollback" (the
# FALSE branch target) sits immediately after "decide" in the declared
# sequence, while "deploy" (the TRUE branch target) is declared last, not
# adjacent at all. A resolver that merely walked `steps[index + 1]` would
# wrongly land on "rollback" regardless of the real, computed outcome —
# only a genuinely branch-aware resolver reaches "deploy" when the
# condition is true.
_DECISION_DEFINITION = WorkflowDefinition.model_validate(
    {
        "id": "se.decision_pipeline",
        "name": "Decision Pipeline",
        "description": "Analyze, decide, then branch to deploy or rollback.",
        "version": "1.0.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [
            {"id": "analyze", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {
                "id": "decide",
                "type": "decision",
                "condition": {"sourceStepId": "analyze", "field": "passed", "equals": True},
                "branches": {"true": "deploy", "false": "rollback"},
            },
            {"id": "rollback", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "deploy", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
        "failureHandling": {"onError": "halt"},
    }
)


def _step_record(
    *,
    step_name: str,
    status: str,
    attempt: int,
    outputs: dict[str, Any] | None,
    error: dict[str, Any] | None,
) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id=f"stp_fake_{attempt}",
        workflow_id="wf_fake",
        step_name=step_name,
        step_type=StepType.QUALITY_GATE,
        status=status,
        attempt=attempt,
        agent_id=None,
        tool_id=None,
        prompt_id=None,
        prompt_version=None,
        model_alias=None,
        inputs={},
        outputs=outputs,
        error=error,
        idempotency_key=f"wf_fake:{step_name}:{attempt}",
        usage={},
        started_at=now,
        completed_at=now,
    )


def _instance(
    *,
    workflow_id: str,
    status: WorkflowInstanceStatus,
    inputs: dict[str, Any],
    last_event_seq: int,
    current_step_id: str | None = None,
) -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id=workflow_id,
        definition_id="se.product_creation",
        definition_version="1.0.0",
        status=status,
        current_step_id=current_step_id,
        inputs=inputs,
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user-42",
        last_event_seq=last_event_seq,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


class _FakeRepository:
    """Records every call made to it; never touches a database. Holds
    just enough state (an in-memory instance) for `advance()` tests to
    read a realistic `current_step_id` back via `get_instance`."""

    def __init__(
        self,
        instance: WorkflowInstance | None = None,
        steps: list[WorkflowStepRecord] | None = None,
    ) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.transition_calls: list[dict[str, Any]] = []
        self.advance_calls: list[dict[str, Any]] = []
        self.reset_calls: list[dict[str, Any]] = []
        self.record_failed_attempt_calls: list[dict[str, Any]] = []
        self._instance = instance
        self._steps = steps or []

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
    ) -> WorkflowInstance:
        self.create_calls.append(
            {
                "definition_id": definition_id,
                "definition_version": definition_version,
                "inputs": inputs,
                "principal_id": principal_id,
            }
        )
        return _instance(
            workflow_id="wf_fake",
            status=WorkflowInstanceStatus.CREATED,
            inputs=inputs,
            last_event_seq=1,
        )

    async def transition_to_running(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance:
        self.transition_calls.append(
            {
                "workflow_id": workflow_id,
                "reason": reason,
                "triggering_event_id": triggering_event_id,
            }
        )
        return _instance(
            workflow_id=workflow_id,
            status=WorkflowInstanceStatus.RUNNING,
            inputs={},
            last_event_seq=2,
        )

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return self._instance

    async def advance_workflow(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        next_step: WorkflowStep | None,
        outputs: dict[str, Any],
    ) -> WorkflowInstance:
        self.advance_calls.append(
            {
                "workflow_id": workflow_id,
                "definition_id": definition_id,
                "definition_version": definition_version,
                "expected_current_step_id": expected_current_step_id,
                "next_step_id": next_step.id if next_step else None,
                "outputs": outputs,
            }
        )
        if next_step is not None:
            return _instance(
                workflow_id=workflow_id,
                status=WorkflowInstanceStatus.RUNNING,
                inputs={},
                last_event_seq=99,
                current_step_id=next_step.id,
            )
        return _instance(
            workflow_id=workflow_id,
            status=WorkflowInstanceStatus.COMPLETED,
            inputs={},
            last_event_seq=100,
            current_step_id=expected_current_step_id,
        )

    async def reset_current_step(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        retry_to_step_id: str | None,
        reason: str,
    ) -> WorkflowInstance:
        self.reset_calls.append(
            {
                "workflow_id": workflow_id,
                "definition_id": definition_id,
                "definition_version": definition_version,
                "expected_current_step_id": expected_current_step_id,
                "retry_to_step_id": retry_to_step_id,
                "reason": reason,
            }
        )
        return _instance(
            workflow_id=workflow_id,
            status=WorkflowInstanceStatus.RUNNING,
            inputs={},
            last_event_seq=99,
            current_step_id=retry_to_step_id,
        )

    async def record_failed_attempt(
        self,
        *,
        workflow_id: str,
        definition_id: str,
        definition_version: str,
        expected_current_step_id: str | None,
        step: WorkflowStep,
        error: dict[str, Any],
    ) -> None:
        self.record_failed_attempt_calls.append(
            {
                "workflow_id": workflow_id,
                "definition_id": definition_id,
                "definition_version": definition_version,
                "expected_current_step_id": expected_current_step_id,
                "step_id": step.id,
                "error": error,
            }
        )

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        return self._steps

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")

    async def list_runnable_instances(self, *, limit: int) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


class _FakeStepExecutor:
    """Records every step it was asked to execute; never does real work.
    ``error``, when supplied, makes ``execute`` raise it instead of
    returning — the real caller (`WorkflowInstanceService.advance`) is
    what needs a genuinely raising executor to prove it records a
    failed attempt before re-raising."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.executed_steps: list[WorkflowStep] = []
        self.received_workflow_ids: list[str | None] = []
        self._error = error

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        self.executed_steps.append(step)
        self.received_workflow_ids.append(workflow_id)
        if self._error is not None:
            raise self._error
        return {}


class _FakeDefinitionCatalog:
    """Records every registration call; never touches a database. Can be
    told to raise, to prove registration failure stops instance creation
    before the repository is ever called."""

    def __init__(self, error: Exception | None = None) -> None:
        self.register_calls: list[dict[str, Any]] = []
        self._error = error

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None:
        self.register_calls.append({"definition_id": definition.id, "pack_id": pack_id})
        if self._error is not None:
            raise self._error

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None:
        raise NotImplementedError("not exercised by these tests")


class _FakeGateResultRecorder:
    """Records every call made to it; never touches a database."""

    def __init__(self) -> None:
        self.record_calls: list[dict[str, Any]] = []

    async def record(
        self, *, workflow_id: str, gate_version: str, step: WorkflowStepRecord
    ) -> None:
        self.record_calls.append(
            {"workflow_id": workflow_id, "gate_version": gate_version, "step": step}
        )


def _service(
    instance: WorkflowInstance | None = None,
    step_executor: _FakeStepExecutor | None = None,
    definition_catalog: _FakeDefinitionCatalog | None = None,
    steps: list[WorkflowStepRecord] | None = None,
    gate_result_recorder: _FakeGateResultRecorder | None = None,
) -> tuple[WorkflowInstanceService, _FakeRepository, _FakeStepExecutor, _FakeDefinitionCatalog]:
    repository = _FakeRepository(instance, steps)
    step_executor = step_executor or _FakeStepExecutor()
    definition_catalog = definition_catalog or _FakeDefinitionCatalog()
    return (
        WorkflowInstanceService(
            repository, step_executor, definition_catalog, gate_result_recorder
        ),
        repository,
        step_executor,
        definition_catalog,
    )


@pytest.mark.asyncio
async def test_valid_request_is_delegated_to_the_repository() -> None:
    service, repository, _, definition_catalog = _service()

    instance = await service.create_instance(
        definition=_DEFINITION,
        inputs={"specPath": "specs/product.md"},
        principal_id="user-42",
        pack_id="se.software_engineering",
    )

    assert instance.workflow_id == "wf_fake"
    assert instance.status == WorkflowInstanceStatus.CREATED
    assert len(repository.create_calls) == 1
    assert repository.create_calls[0]["definition_id"] == "se.product_creation"
    assert repository.create_calls[0]["principal_id"] == "user-42"
    assert definition_catalog.register_calls == [
        {"definition_id": "se.product_creation", "pack_id": "se.software_engineering"}
    ]


@pytest.mark.asyncio
async def test_create_instance_registers_the_definition_before_creating_the_instance() -> None:
    """If registration fails, the instance is never created — the two
    writes are sequential, not independent."""
    failing_catalog = _FakeDefinitionCatalog(error=RuntimeError("registration backend down"))
    service, repository, _, definition_catalog = _service(definition_catalog=failing_catalog)

    with pytest.raises(RuntimeError, match="registration backend down"):
        await service.create_instance(
            definition=_DEFINITION,
            inputs={"specPath": "specs/product.md"},
            principal_id="user-42",
            pack_id="se.software_engineering",
        )

    assert len(definition_catalog.register_calls) == 1
    assert repository.create_calls == []


@pytest.mark.asyncio
async def test_invalid_inputs_are_rejected_before_the_repository_is_called() -> None:
    service, repository, _, definition_catalog = _service()

    with pytest.raises(WorkflowInputValidationError):
        await service.create_instance(
            definition=_DEFINITION,
            inputs={},
            principal_id="user-42",
            pack_id="se.software_engineering",
        )

    assert repository.create_calls == []
    assert definition_catalog.register_calls == []


@pytest.mark.asyncio
async def test_blank_principal_is_rejected_before_the_repository_is_called() -> None:
    service, repository, _, definition_catalog = _service()

    with pytest.raises(WorkflowInputValidationError):
        await service.create_instance(
            definition=_DEFINITION,
            inputs={"specPath": "specs/product.md"},
            principal_id="   ",
            pack_id="se.software_engineering",
        )

    assert repository.create_calls == []
    assert definition_catalog.register_calls == []


@pytest.mark.asyncio
async def test_blank_pack_id_is_rejected_before_the_repository_is_called() -> None:
    service, repository, _, definition_catalog = _service()

    with pytest.raises(WorkflowInputValidationError):
        await service.create_instance(
            definition=_DEFINITION,
            inputs={"specPath": "specs/product.md"},
            principal_id="user-42",
            pack_id="   ",
        )

    assert repository.create_calls == []
    assert definition_catalog.register_calls == []


@pytest.mark.asyncio
async def test_start_is_delegated_to_the_repository() -> None:
    service, repository, _, _ = _service()

    instance = await service.start(workflow_id="wf_fake", reason="worker picked it up")

    assert instance.status == WorkflowInstanceStatus.RUNNING
    assert instance.last_event_seq == 2
    assert repository.transition_calls == [
        {"workflow_id": "wf_fake", "reason": "worker picked it up", "triggering_event_id": None}
    ]


@pytest.mark.asyncio
async def test_start_passes_through_an_optional_triggering_event_id() -> None:
    service, repository, _, _ = _service()

    await service.start(
        workflow_id="wf_fake", reason="lease acquired", triggering_event_id="evt_lease"
    )

    assert repository.transition_calls[0]["triggering_event_id"] == "evt_lease"


@pytest.mark.asyncio
async def test_blank_reason_is_rejected_before_the_repository_is_called() -> None:
    service, repository, _, _ = _service()

    with pytest.raises(WorkflowInputValidationError):
        await service.start(workflow_id="wf_fake", reason="   ")

    assert repository.transition_calls == []


@pytest.mark.asyncio
async def test_advance_resolves_and_executes_the_first_step_when_none_has_run() -> None:
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    service, repository, step_executor, _ = _service(instance=current)

    result = await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert result.current_step_id == "analyze_requirements"
    assert [s.id for s in step_executor.executed_steps] == ["analyze_requirements"]
    assert repository.advance_calls[0]["expected_current_step_id"] is None
    assert repository.advance_calls[0]["next_step_id"] == "analyze_requirements"


@pytest.mark.asyncio
async def test_advance_forwards_the_workflow_id_to_the_step_executor() -> None:
    # The wiring the Context Manager's first real slice needs:
    # AgentStepExecutor cannot ask for this instance's own state
    # without knowing which instance is being advanced.
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    service, _, step_executor, _ = _service(instance=current)

    await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert step_executor.received_workflow_ids == ["wf_fake"]


@pytest.mark.asyncio
async def test_advance_resolves_the_second_step_after_the_first_has_run() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="analyze_requirements",
    )
    service, repository, step_executor, _ = _service(instance=current)

    result = await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert result.current_step_id == "implement"
    assert [s.id for s in step_executor.executed_steps] == ["implement"]
    assert repository.advance_calls[0]["expected_current_step_id"] == "analyze_requirements"
    assert repository.advance_calls[0]["next_step_id"] == "implement"


@pytest.mark.asyncio
async def test_advance_completes_the_workflow_after_the_final_step() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=6,
        current_step_id="implement",
    )
    service, repository, step_executor, _ = _service(instance=current)

    result = await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert result.status == WorkflowInstanceStatus.COMPLETED
    assert step_executor.executed_steps == []  # nothing left to execute
    assert repository.advance_calls[0]["expected_current_step_id"] == "implement"
    assert repository.advance_calls[0]["next_step_id"] is None


@pytest.mark.asyncio
async def test_advance_records_a_failed_attempt_when_the_executor_raises_then_reraises() -> None:
    """The real proof this feature step exists for: a step executor
    that genuinely raises still leaves a real, recorded trace
    (`record_failed_attempt`) — closing quality_gate_engine.md §9's own
    recording requirement — and the *original* exception still
    propagates completely unchanged, so every existing caller
    (`WorkflowAdvanceRunner`'s own retry/failure logic) is unaffected."""
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    failure = QualityGateFailedError("gate failed", gate_step_id="analyze_requirements")
    service, repository, step_executor, _ = _service(
        instance=current, step_executor=_FakeStepExecutor(error=failure)
    )

    with pytest.raises(QualityGateFailedError) as exc_info:
        await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert exc_info.value is failure  # the exact same exception, not a copy or a wrapper
    assert repository.advance_calls == []  # advance_workflow is never reached
    assert repository.record_failed_attempt_calls == [
        {
            "workflow_id": "wf_fake",
            "definition_id": "se.product_creation",
            "definition_version": "1.0.0",
            "expected_current_step_id": None,
            "step_id": "analyze_requirements",
            "error": {"type": "QualityGateFailedError", "message": "gate failed"},
        }
    ]


@pytest.mark.asyncio
async def test_advance_records_no_failed_attempt_when_the_executor_succeeds() -> None:
    """Zero regression, made explicit: a normal, successful advance
    never calls `record_failed_attempt` at all."""
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    service, repository, _, _ = _service(instance=current)

    await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert repository.record_failed_attempt_calls == []


@pytest.mark.asyncio
async def test_advance_records_a_gate_result_when_a_quality_gate_step_passes() -> None:
    """The real proof this feature step exists for: a passing
    `quality_gate` step's own real, just-written `WorkflowStepRecord`
    is read back and handed to the injected `GateResultRecorder` —
    `gate_version` sourced from the real `definition.version`, never
    invented."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="build",
    )
    passing_output = {"gateId": "gate", "sourceStepId": "build", "passed": True}
    recorder = _FakeGateResultRecorder()
    service, repository, _, _ = _service(
        instance=current,
        step_executor=_FakeStepExecutor(),
        steps=[
            _step_record(
                step_name="gate", status="completed", attempt=1, outputs=passing_output, error=None
            )
        ],
        gate_result_recorder=recorder,
    )
    # `_FakeStepExecutor()` (no error) always returns `{}` — close enough
    # for this test's own purpose, since `_maybe_record_gate_result`
    # reads the just-written row back from `list_steps`, not from the
    # executor's own return value directly.

    await service.advance(workflow_id="wf_fake", definition=_GATE_DEFINITION)

    assert len(recorder.record_calls) == 1
    call = recorder.record_calls[0]
    assert call["workflow_id"] == "wf_fake"
    assert call["gate_version"] == "1.2.0"  # _GATE_DEFINITION.version, not invented
    assert call["step"].step_name == "gate"
    assert call["step"].status == "completed"
    assert call["step"].outputs == passing_output


@pytest.mark.asyncio
async def test_advance_records_a_gate_result_when_a_quality_gate_step_fails() -> None:
    """The other real proof: a failing `quality_gate` step's own real,
    just-written, `status="failed"` row (with real `error` detail) is
    also read back and recorded — not only the passing case — and the
    original exception still propagates unchanged."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="build",
    )
    failure = QualityGateFailedError("gate failed", gate_step_id="gate")
    real_error = {"type": "QualityGateFailedError", "message": "gate failed"}
    recorder = _FakeGateResultRecorder()
    service, repository, _, _ = _service(
        instance=current,
        step_executor=_FakeStepExecutor(error=failure),
        steps=[
            _step_record(
                step_name="gate", status="failed", attempt=1, outputs=None, error=real_error
            )
        ],
        gate_result_recorder=recorder,
    )

    with pytest.raises(QualityGateFailedError):
        await service.advance(workflow_id="wf_fake", definition=_GATE_DEFINITION)

    assert len(recorder.record_calls) == 1
    call = recorder.record_calls[0]
    assert call["gate_version"] == "1.2.0"
    assert call["step"].step_name == "gate"
    assert call["step"].status == "failed"
    assert call["step"].error == real_error


@pytest.mark.asyncio
async def test_advance_does_not_record_a_gate_result_for_a_non_gate_step() -> None:
    """A plain `agent` step never reaches the recorder, even when one is
    injected — `list_steps` (which would raise for an unconfigured
    workflow_id in the real repository) is never even called."""
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    recorder = _FakeGateResultRecorder()
    service, repository, _, _ = _service(instance=current, gate_result_recorder=recorder)

    await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert recorder.record_calls == []


@pytest.mark.asyncio
async def test_advance_does_not_record_an_unconfigured_gates_empty_result() -> None:
    """`QualityGateStepExecutor`'s own documented no-op case (a
    `quality_gate` step absent from its `gate_sources`) returns `{}` —
    genuinely never evaluated, so no `evaluation.gate_results` row
    should be written for it, even though the step itself completes
    successfully."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="build",
    )
    recorder = _FakeGateResultRecorder()
    service, repository, _, _ = _service(
        instance=current,
        step_executor=_FakeStepExecutor(),
        steps=[
            _step_record(step_name="gate", status="completed", attempt=1, outputs={}, error=None)
        ],
        gate_result_recorder=recorder,
    )

    await service.advance(workflow_id="wf_fake", definition=_GATE_DEFINITION)

    assert recorder.record_calls == []


def _decision_step_executor(repository: _FakeRepository) -> DispatchingStepExecutor:
    """A real `DispatchingStepExecutor` wired with a real
    `DecisionStepExecutor` against `repository` — every non-decision
    step still dispatches to a fresh `_FakeStepExecutor`, exactly as
    every other test in this file already exercises."""
    return DispatchingStepExecutor(
        agent_executor=_FakeStepExecutor(),
        tool_executor=_FakeStepExecutor(),
        default_executor=NoOpStepExecutor(),
        decision_executor=DecisionStepExecutor(repository),
    )


@pytest.mark.asyncio
async def test_a_decision_step_genuinely_computes_and_persists_its_own_real_branch_outcome() -> (
    None
):
    """The real proof P02-S01-M05-T09 exists for, part one: the decision
    step's own execution reads its source step's already-persisted
    output, evaluates the declared condition for real, and persists a
    real, computed branch decision — not a hardcoded or ignored value."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="analyze",
    )
    repository = _FakeRepository(
        current,
        steps=[
            _step_record(
                step_name="analyze",
                status="completed",
                attempt=1,
                outputs={"passed": True},
                error=None,
            )
        ],
    )
    service = WorkflowInstanceService(
        repository, _decision_step_executor(repository), _FakeDefinitionCatalog()
    )

    await service.advance(workflow_id="wf_fake", definition=_DECISION_DEFINITION)

    assert len(repository.advance_calls) == 1
    call = repository.advance_calls[0]
    assert call["next_step_id"] == "decide"
    assert call["outputs"] == {"outcome": True, "branch": "deploy"}


@pytest.mark.asyncio
async def test_advance_genuinely_branches_to_the_true_target_skipping_the_adjacent_false_step() -> (
    None
):
    """The real proof, part two — and the one that actually matters: a
    *subsequent* `advance()` call reads the decision step's own
    just-persisted `branch` output and resolves to `deploy`, even though
    `rollback` is the step immediately after `decide` in the declared
    sequence. A resolver that merely walked the list positionally would
    land on `rollback` regardless of the real outcome; only a genuinely
    branch-aware one reaches `deploy`."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="decide",
    )
    repository = _FakeRepository(
        current,
        steps=[
            _step_record(
                step_name="analyze",
                status="completed",
                attempt=1,
                outputs={"passed": True},
                error=None,
            ),
            _step_record(
                step_name="decide",
                status="completed",
                attempt=1,
                outputs={"outcome": True, "branch": "deploy"},
                error=None,
            ),
        ],
    )
    agent_executor = _FakeStepExecutor()
    step_executor = DispatchingStepExecutor(
        agent_executor=agent_executor,
        tool_executor=_FakeStepExecutor(),
        default_executor=NoOpStepExecutor(),
        decision_executor=DecisionStepExecutor(repository),
    )
    service = WorkflowInstanceService(repository, step_executor, _FakeDefinitionCatalog())

    result = await service.advance(workflow_id="wf_fake", definition=_DECISION_DEFINITION)

    assert result.current_step_id == "deploy"
    assert repository.advance_calls[0]["next_step_id"] == "deploy"
    assert [s.id for s in agent_executor.executed_steps] == ["deploy"]


@pytest.mark.asyncio
async def test_advance_genuinely_branches_to_the_false_target_when_the_condition_is_false() -> None:
    """The mirrored outcome — combined with the true-branch test above,
    this proves the resolver follows the real, computed condition either
    way, not a fixed direction."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="decide",
    )
    repository = _FakeRepository(
        current,
        steps=[
            _step_record(
                step_name="analyze",
                status="completed",
                attempt=1,
                outputs={"passed": False},
                error=None,
            ),
            _step_record(
                step_name="decide",
                status="completed",
                attempt=1,
                outputs={"outcome": False, "branch": "rollback"},
                error=None,
            ),
        ],
    )
    agent_executor = _FakeStepExecutor()
    step_executor = DispatchingStepExecutor(
        agent_executor=agent_executor,
        tool_executor=_FakeStepExecutor(),
        default_executor=NoOpStepExecutor(),
        decision_executor=DecisionStepExecutor(repository),
    )
    service = WorkflowInstanceService(repository, step_executor, _FakeDefinitionCatalog())

    result = await service.advance(workflow_id="wf_fake", definition=_DECISION_DEFINITION)

    assert result.current_step_id == "rollback"
    assert [s.id for s in agent_executor.executed_steps] == ["rollback"]


@pytest.mark.asyncio
async def test_a_decision_step_whose_source_has_not_run_yet_raises_clearly() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="analyze",
    )
    repository = _FakeRepository(current, steps=[])  # "analyze" never persisted an output

    service = WorkflowInstanceService(
        repository, _decision_step_executor(repository), _FakeDefinitionCatalog()
    )

    with pytest.raises(DecisionConditionError, match="no persisted output yet"):
        await service.advance(workflow_id="wf_fake", definition=_DECISION_DEFINITION)


@pytest.mark.asyncio
async def test_advance_rejects_a_missing_instance() -> None:
    service, repository, step_executor, _ = _service(instance=None)

    with pytest.raises(WorkflowInvalidTransitionError, match="does not exist"):
        await service.advance(workflow_id="wf_missing", definition=_DEFINITION)

    assert repository.advance_calls == []
    assert step_executor.executed_steps == []


@pytest.mark.asyncio
async def test_advance_rejects_a_current_step_not_in_the_definition() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="not_a_real_step",
    )
    service, repository, step_executor, _ = _service(instance=current)

    with pytest.raises(WorkflowInvalidTransitionError, match="not_a_real_step"):
        await service.advance(workflow_id="wf_fake", definition=_DEFINITION)

    assert repository.advance_calls == []
    assert step_executor.executed_steps == []


@pytest.mark.asyncio
async def test_advance_rejects_a_definition_with_no_steps() -> None:
    # WorkflowDefinition itself refuses an empty `steps` list at load
    # time (a previously approved step's validation); `model_copy`
    # bypasses validators, so this is the only way to construct a
    # definition object that exercises this service-level guard.
    empty_definition = _DEFINITION.model_copy(update={"steps": []})
    current = _instance(
        workflow_id="wf_fake", status=WorkflowInstanceStatus.RUNNING, inputs={}, last_event_seq=2
    )
    service, repository, step_executor, _ = _service(instance=current)

    with pytest.raises(WorkflowInvalidTransitionError, match="no steps"):
        await service.advance(workflow_id="wf_fake", definition=empty_definition)

    assert repository.advance_calls == []
    assert step_executor.executed_steps == []


@pytest.mark.asyncio
async def test_retry_after_step_failure_resets_to_the_step_before_the_retry_target() -> None:
    """`_DEFINITION` is `analyze_requirements` -> `implement`; retrying
    from `implement` must reset `current_step_id` back to
    `analyze_requirements`, so the *next* `advance()` call re-executes
    `implement`, not skip past it."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="implement",
    )
    service, repository, _, _ = _service(instance=current)

    result = await service.retry_after_step_failure(
        workflow_id="wf_fake",
        definition=_DEFINITION,
        retry_from_step_id="implement",
        reason="quality gate failed, retrying",
    )

    assert result.current_step_id == "analyze_requirements"
    assert repository.reset_calls == [
        {
            "workflow_id": "wf_fake",
            "definition_id": "se.product_creation",
            "definition_version": "1.0.0",
            "expected_current_step_id": "implement",
            "retry_to_step_id": "analyze_requirements",
            "reason": "quality gate failed, retrying",
        }
    ]


@pytest.mark.asyncio
async def test_retry_after_step_failure_resets_to_none_when_the_target_is_the_first_step() -> None:
    """Retrying from the definition's own first step must reset
    `current_step_id` to `None` — the same "haven't started yet"
    meaning `_resolve_next_step` already gives that value."""
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=2,
        current_step_id="analyze_requirements",
    )
    service, repository, _, _ = _service(instance=current)

    result = await service.retry_after_step_failure(
        workflow_id="wf_fake",
        definition=_DEFINITION,
        retry_from_step_id="analyze_requirements",
        reason="quality gate failed, retrying",
    )

    assert result.current_step_id is None
    assert repository.reset_calls[0]["retry_to_step_id"] is None


@pytest.mark.asyncio
async def test_retry_after_step_failure_rejects_a_missing_instance() -> None:
    service, repository, _, _ = _service(instance=None)

    with pytest.raises(WorkflowInvalidTransitionError, match="does not exist"):
        await service.retry_after_step_failure(
            workflow_id="wf_missing",
            definition=_DEFINITION,
            retry_from_step_id="implement",
            reason="quality gate failed, retrying",
        )

    assert repository.reset_calls == []


@pytest.mark.asyncio
async def test_retry_after_step_failure_rejects_a_step_not_in_the_definition() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="implement",
    )
    service, repository, _, _ = _service(instance=current)

    with pytest.raises(WorkflowInvalidTransitionError, match="not_a_real_step"):
        await service.retry_after_step_failure(
            workflow_id="wf_fake",
            definition=_DEFINITION,
            retry_from_step_id="not_a_real_step",
            reason="quality gate failed, retrying",
        )

    assert repository.reset_calls == []
