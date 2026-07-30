"""Unit tests for WorkflowInstanceService: validate-then-delegate, with a
fake repository and a fake step executor — no database (ADR-0004:
interface-driven, so fake Protocol implementations are legitimate
substitutes in a unit test)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
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

    def __init__(self, instance: WorkflowInstance | None = None) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.transition_calls: list[dict[str, Any]] = []
        self.advance_calls: list[dict[str, Any]] = []
        self.reset_calls: list[dict[str, Any]] = []
        self._instance = instance

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

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


class _FakeStepExecutor:
    """Records every step it was asked to execute; never does real work."""

    def __init__(self) -> None:
        self.executed_steps: list[WorkflowStep] = []
        self.received_workflow_ids: list[str | None] = []

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        self.executed_steps.append(step)
        self.received_workflow_ids.append(workflow_id)
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


def _service(
    instance: WorkflowInstance | None = None,
    step_executor: _FakeStepExecutor | None = None,
    definition_catalog: _FakeDefinitionCatalog | None = None,
) -> tuple[WorkflowInstanceService, _FakeRepository, _FakeStepExecutor, _FakeDefinitionCatalog]:
    repository = _FakeRepository(instance)
    step_executor = step_executor or _FakeStepExecutor()
    definition_catalog = definition_catalog or _FakeDefinitionCatalog()
    return (
        WorkflowInstanceService(repository, step_executor, definition_catalog),
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
async def test_retry_after_gate_failure_resets_to_the_step_before_the_retry_target() -> None:
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

    result = await service.retry_after_gate_failure(
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
async def test_retry_after_gate_failure_resets_to_none_when_the_target_is_the_first_step() -> None:
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

    result = await service.retry_after_gate_failure(
        workflow_id="wf_fake",
        definition=_DEFINITION,
        retry_from_step_id="analyze_requirements",
        reason="quality gate failed, retrying",
    )

    assert result.current_step_id is None
    assert repository.reset_calls[0]["retry_to_step_id"] is None


@pytest.mark.asyncio
async def test_retry_after_gate_failure_rejects_a_missing_instance() -> None:
    service, repository, _, _ = _service(instance=None)

    with pytest.raises(WorkflowInvalidTransitionError, match="does not exist"):
        await service.retry_after_gate_failure(
            workflow_id="wf_missing",
            definition=_DEFINITION,
            retry_from_step_id="implement",
            reason="quality gate failed, retrying",
        )

    assert repository.reset_calls == []


@pytest.mark.asyncio
async def test_retry_after_gate_failure_rejects_a_step_not_in_the_definition() -> None:
    current = _instance(
        workflow_id="wf_fake",
        status=WorkflowInstanceStatus.RUNNING,
        inputs={},
        last_event_seq=4,
        current_step_id="implement",
    )
    service, repository, _, _ = _service(instance=current)

    with pytest.raises(WorkflowInvalidTransitionError, match="not_a_real_step"):
        await service.retry_after_gate_failure(
            workflow_id="wf_fake",
            definition=_DEFINITION,
            retry_from_step_id="not_a_real_step",
            reason="quality gate failed, retrying",
        )

    assert repository.reset_calls == []
