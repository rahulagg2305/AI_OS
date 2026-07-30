"""Unit tests for WorkflowAdvanceRunner: acquire → advance once →
release, with real services backed by fake repositories — no database
(ADR-0004: interface-driven, so fake Protocol implementations are
legitimate substitutes in a unit test)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunOutcome,
)
from ai_os_kernel.workflow_engine.errors import (
    QualityGateFailedError,
    WorkflowInputValidationError,
    WorkflowInvalidTransitionError,
    WorkflowLeaseUnavailableError,
)
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import WorkflowLease, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_DEFINITION = WorkflowDefinition.model_validate(
    {
        "id": "se.product_creation",
        "name": "Full Product Creation",
        "description": "Turn a structured specification into working software.",
        "version": "1.0.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            }
        ],
        "failureHandling": {"onError": "escalate"},
    }
)

_TWO_STEP_DEFINITION = WorkflowDefinition.model_validate(
    {
        "id": "se.product_creation",
        "name": "Full Product Creation",
        "description": "Turn a structured specification into working software.",
        "version": "1.0.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [
            {"id": "step_a", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "step_b", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
        "failureHandling": {"onError": "escalate"},
    }
)

_GATE_DEFINITION = WorkflowDefinition.model_validate(
    {
        "id": "se.gated_pipeline",
        "name": "Gated Pipeline",
        "description": "One agent step, then one real, blocking quality gate.",
        "version": "1.0.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [
            {"id": "build", "type": "agent", "agentId": "se.software_engineering/build"},
            {"id": "gate", "type": "quality_gate"},
        ],
        "failureHandling": {"onError": "halt"},
        "retryPolicy": {"maxAttempts": 2, "maxDurationSeconds": 60.0},
    }
)

_GATE_DEFINITION_NO_RETRY_POLICY = _GATE_DEFINITION.model_copy(update={"retry_policy": None})


def _instance(
    *,
    current_step_id: str | None,
    status: WorkflowInstanceStatus = WorkflowInstanceStatus.RUNNING,
) -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id="wf_fake",
        definition_id="se.product_creation",
        definition_version="1.0.0",
        status=status,
        current_step_id=current_step_id,
        inputs={},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user-42",
        last_event_seq=2,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def _lease(workflow_id: str, worker_id: str) -> WorkflowLease:
    now = datetime.now(UTC)
    return WorkflowLease(
        lease_id="lease_fake",
        workflow_id=workflow_id,
        worker_id=worker_id,
        acquired_at=now,
        expires_at=now,
        heartbeat_at=now,
    )


class _FakeInstanceRepository:
    """Only `get_instance`/`advance_workflow` are exercised; `create`
    and `transition_to_running` are implemented for Protocol
    conformance but never called by these tests."""

    def __init__(self, *, advance_error: Exception | None = None) -> None:
        self.advance_calls: list[dict[str, Any]] = []
        self._advance_error = advance_error
        self._instance = _instance(current_step_id=None)

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
    ) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def transition_to_running(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

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
            }
        )
        if self._advance_error is not None:
            raise self._advance_error
        return _instance(current_step_id=next_step.id if next_step else None)

    async def reset_current_step(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def record_failed_attempt(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


class _FakeLeaseRepository:
    """Only `acquire`/`release` are exercised; `renew` is implemented
    for Protocol conformance but never called by these tests."""

    def __init__(self, *, acquire_error: Exception | None = None) -> None:
        self.acquire_calls: list[dict[str, Any]] = []
        self.release_calls: list[dict[str, Any]] = []
        self._acquire_error = acquire_error

    async def acquire(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        self.acquire_calls.append(
            {
                "workflow_id": workflow_id,
                "worker_id": worker_id,
                "lease_duration_seconds": lease_duration_seconds,
            }
        )
        if self._acquire_error is not None:
            raise self._acquire_error
        return _lease(workflow_id, worker_id)

    async def renew(
        self, *, workflow_id: str, worker_id: str, lease_duration_seconds: int
    ) -> WorkflowLease:
        raise NotImplementedError("not exercised by these tests")

    async def release(self, *, workflow_id: str, worker_id: str) -> None:
        self.release_calls.append({"workflow_id": workflow_id, "worker_id": worker_id})

    async def reap_expired(self, *, limit: int) -> list[WorkflowLease]:
        raise NotImplementedError("not exercised by these tests")


class _StatefulInstanceRepository:
    """Unlike `_FakeInstanceRepository` above, tracks `current_step_id`
    and `status` across calls — needed to exercise `run_to_completion`,
    which depends on each `advance()` seeing the *previous* call's
    result via `get_instance`, exactly as the real repository does."""

    def __init__(self, *, fail_on_call_number: int | None = None) -> None:
        self.advance_calls: list[dict[str, Any]] = []
        self._fail_on_call_number = fail_on_call_number
        self._current_step_id: str | None = None
        self._status = WorkflowInstanceStatus.RUNNING

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
    ) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def transition_to_running(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return _instance(current_step_id=self._current_step_id, status=self._status)

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
        self.advance_calls.append({"next_step_id": next_step.id if next_step else None})
        if self._fail_on_call_number == len(self.advance_calls):
            raise WorkflowInvalidTransitionError("simulated failure mid-run")
        self._current_step_id = next_step.id if next_step else self._current_step_id
        self._status = (
            WorkflowInstanceStatus.RUNNING
            if next_step is not None
            else WorkflowInstanceStatus.COMPLETED
        )
        return _instance(current_step_id=self._current_step_id, status=self._status)

    async def reset_current_step(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def record_failed_attempt(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


class _GateRetryInstanceRepository:
    """A `build` step that always succeeds, feeding a `gate` step that
    fails on its own first N attempts, then succeeds — a real,
    controllable flaky condition (a counter), not a coin flip. Also
    implements `reset_current_step` for real, so a genuine retry
    genuinely re-executes `build`."""

    def __init__(self, *, gate_failures_before_success: int) -> None:
        self.advance_calls: list[str | None] = []
        self.reset_calls: list[dict[str, Any]] = []
        self._current_step_id: str | None = None
        self._status = WorkflowInstanceStatus.RUNNING
        self._gate_attempts = 0
        self._gate_failures_before_success = gate_failures_before_success

    async def create(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def transition_to_running(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return _instance(current_step_id=self._current_step_id, status=self._status)

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
        self.advance_calls.append(next_step.id if next_step else None)
        if next_step is not None and next_step.id == "gate":
            self._gate_attempts += 1
            if self._gate_attempts <= self._gate_failures_before_success:
                raise QualityGateFailedError("gate failed", gate_step_id="gate")
        self._current_step_id = next_step.id if next_step else self._current_step_id
        self._status = (
            WorkflowInstanceStatus.RUNNING
            if next_step is not None
            else WorkflowInstanceStatus.COMPLETED
        )
        return _instance(current_step_id=self._current_step_id, status=self._status)

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
                "expected_current_step_id": expected_current_step_id,
                "retry_to_step_id": retry_to_step_id,
                "reason": reason,
            }
        )
        self._current_step_id = retry_to_step_id
        return _instance(current_step_id=self._current_step_id, status=self._status)

    async def record_failed_attempt(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")


class _FakeDefinitionCatalog:
    """Never exercised by these tests (none call `create_instance`);
    exists only to satisfy `WorkflowInstanceService`'s constructor."""

    async def register(self, *, definition: WorkflowDefinition, pack_id: str) -> None:
        raise NotImplementedError("not exercised by these tests")


def _runner(
    instance_repository: _FakeInstanceRepository | _StatefulInstanceRepository,
    lease_repository: _FakeLeaseRepository,
) -> WorkflowAdvanceRunner:
    return WorkflowAdvanceRunner(
        WorkflowInstanceService(instance_repository, NoOpStepExecutor(), _FakeDefinitionCatalog()),
        WorkflowLeaseService(lease_repository),
    )


@pytest.mark.asyncio
async def test_run_once_acquires_advances_and_releases_in_order() -> None:
    instance_repository = _FakeInstanceRepository()
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    result = await runner.run_once(
        workflow_id="wf_fake",
        definition=_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
    )

    assert result.current_step_id == "analyze_requirements"
    assert lease_repository.acquire_calls == [
        {"workflow_id": "wf_fake", "worker_id": "worker-1", "lease_duration_seconds": 60}
    ]
    assert len(instance_repository.advance_calls) == 1
    assert lease_repository.release_calls == [{"workflow_id": "wf_fake", "worker_id": "worker-1"}]


@pytest.mark.asyncio
async def test_release_still_happens_if_advance_fails() -> None:
    failure = WorkflowInvalidTransitionError("simulated advance failure")
    instance_repository = _FakeInstanceRepository(advance_error=failure)
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    with pytest.raises(WorkflowInvalidTransitionError, match="simulated advance failure"):
        await runner.run_once(
            workflow_id="wf_fake",
            definition=_DEFINITION,
            worker_id="worker-1",
            lease_duration_seconds=60,
        )

    assert lease_repository.release_calls == [{"workflow_id": "wf_fake", "worker_id": "worker-1"}]


@pytest.mark.asyncio
async def test_advance_is_never_called_when_the_lease_cannot_be_acquired() -> None:
    claim_rejected = WorkflowLeaseUnavailableError(
        "workflow instance 'wf_fake' is already leased and not yet expired"
    )
    instance_repository = _FakeInstanceRepository()
    lease_repository = _FakeLeaseRepository(acquire_error=claim_rejected)
    runner = _runner(instance_repository, lease_repository)

    with pytest.raises(WorkflowLeaseUnavailableError, match="already leased"):
        await runner.run_once(
            workflow_id="wf_fake",
            definition=_DEFINITION,
            worker_id="worker-2",
            lease_duration_seconds=60,
        )

    assert instance_repository.advance_calls == []
    assert lease_repository.release_calls == []


@pytest.mark.asyncio
async def test_run_to_completion_reaches_completed_across_multiple_iterations() -> None:
    instance_repository = _StatefulInstanceRepository()
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_TWO_STEP_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
    )

    assert result.outcome is WorkflowRunOutcome.COMPLETED
    # step_a, step_b, then the completing call: three advance() calls.
    assert result.iterations == 3
    assert result.last_instance is not None
    assert result.last_instance.status == WorkflowInstanceStatus.COMPLETED
    assert result.error is None
    # Every acquired lease was released — none left held.
    assert len(lease_repository.acquire_calls) == len(lease_repository.release_calls) == 3


@pytest.mark.asyncio
async def test_max_iterations_bound_prevents_infinite_looping() -> None:
    instance_repository = _StatefulInstanceRepository()
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_TWO_STEP_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=1,
    )

    assert result.outcome is WorkflowRunOutcome.MAX_ITERATIONS_REACHED
    assert result.iterations == 1
    assert result.last_instance is not None
    assert result.last_instance.status != WorkflowInstanceStatus.COMPLETED
    assert len(instance_repository.advance_calls) == 1


@pytest.mark.asyncio
async def test_a_terminal_error_stops_the_loop_and_is_reported_not_raised() -> None:
    instance_repository = _StatefulInstanceRepository(fail_on_call_number=2)
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_TWO_STEP_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
    )

    assert result.outcome is WorkflowRunOutcome.FAILED
    assert result.iterations == 2
    assert isinstance(result.error, WorkflowInvalidTransitionError)
    assert "simulated failure" in str(result.error)
    # The lease from the failed second call was still released.
    assert len(lease_repository.acquire_calls) == len(lease_repository.release_calls) == 2


def _gate_runner(instance_repository: _GateRetryInstanceRepository) -> WorkflowAdvanceRunner:
    return WorkflowAdvanceRunner(
        WorkflowInstanceService(instance_repository, NoOpStepExecutor(), _FakeDefinitionCatalog()),
        WorkflowLeaseService(_FakeLeaseRepository()),
    )


@pytest.mark.asyncio
async def test_a_gate_failure_within_the_retry_bound_eventually_completes() -> None:
    """Fails once, succeeds on the retry — `maxAttempts: 2` allows
    exactly this."""
    instance_repository = _GateRetryInstanceRepository(gate_failures_before_success=1)
    runner = _gate_runner(instance_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_GATE_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
        gate_retry_targets={"gate": "build"},
    )

    assert result.outcome is WorkflowRunOutcome.COMPLETED
    assert result.error is None
    # build, gate (fails), build (retry), gate (passes), complete.
    assert instance_repository.advance_calls == ["build", "gate", "build", "gate", None]
    assert len(instance_repository.reset_calls) == 1
    assert instance_repository.reset_calls[0]["retry_to_step_id"] is None  # build is the first step


@pytest.mark.asyncio
async def test_a_gate_that_fails_every_attempt_exhausts_the_bound_and_fails() -> None:
    """Fails on every attempt — `maxAttempts: 2` allows exactly one
    retry, then genuinely gives up. Not an infinite loop: exactly 2
    real attempts at `gate`, never a third."""
    instance_repository = _GateRetryInstanceRepository(gate_failures_before_success=99)
    runner = _gate_runner(instance_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_GATE_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
        gate_retry_targets={"gate": "build"},
    )

    assert result.outcome is WorkflowRunOutcome.FAILED
    assert isinstance(result.error, QualityGateFailedError)
    assert instance_repository.advance_calls.count("gate") == 2  # maxAttempts, not more
    assert len(instance_repository.reset_calls) == 1  # exactly one retry was granted


@pytest.mark.asyncio
async def test_a_gate_failure_with_no_configured_retry_target_fails_immediately() -> None:
    """`gate_retry_targets` doesn't mention `gate` at all — the default,
    zero-behaviour-change shape every caller except `se.delivery_pipeline`
    has."""
    instance_repository = _GateRetryInstanceRepository(gate_failures_before_success=1)
    runner = _gate_runner(instance_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_GATE_DEFINITION,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
        gate_retry_targets=None,
    )

    assert result.outcome is WorkflowRunOutcome.FAILED
    assert isinstance(result.error, QualityGateFailedError)
    assert instance_repository.advance_calls == ["build", "gate"]
    assert instance_repository.reset_calls == []


@pytest.mark.asyncio
async def test_a_gate_failure_with_no_retry_policy_on_the_definition_fails_immediately() -> None:
    """A configured `gate_retry_targets` entry alone is not enough —
    `definition.retry_policy` must also be declared (the real bound
    comes from there, never invented by the runner)."""
    instance_repository = _GateRetryInstanceRepository(gate_failures_before_success=1)
    runner = _gate_runner(instance_repository)

    result = await runner.run_to_completion(
        workflow_id="wf_fake",
        definition=_GATE_DEFINITION_NO_RETRY_POLICY,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
        gate_retry_targets={"gate": "build"},
    )

    assert result.outcome is WorkflowRunOutcome.FAILED
    assert instance_repository.reset_calls == []


@pytest.mark.asyncio
async def test_non_positive_max_iterations_is_rejected_before_the_loop_starts() -> None:
    instance_repository = _StatefulInstanceRepository()
    lease_repository = _FakeLeaseRepository()
    runner = _runner(instance_repository, lease_repository)

    with pytest.raises(WorkflowInputValidationError, match="max_iterations"):
        await runner.run_to_completion(
            workflow_id="wf_fake",
            definition=_TWO_STEP_DEFINITION,
            worker_id="worker-1",
            lease_duration_seconds=60,
            max_iterations=0,
        )

    assert instance_repository.advance_calls == []
    assert lease_repository.acquire_calls == []
