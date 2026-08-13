"""Unit tests for QualityGateStepExecutor's own evaluation logic — a
fake repository throughout, isolating "does the gate correctly read a
source step's real output and decide pass/fail" from any real
database (ADR-0004: interface-driven, so a fake Protocol implementation
is a legitimate substitute in a unit test). The end-to-end proof that
this genuinely halts `se.delivery_pipeline` lives in
`tests/integration/workflow_engine/test_delivery_pipeline.py`."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, Literal

import pytest

from ai_os_kernel.quality_gate_engine.errors import GateNotRegisteredError
from ai_os_kernel.quality_gate_engine.registry import GateDefinition, InMemoryGateRegistry
from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.quality_gate import GateCheck, QualityGateStepExecutor
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord


def _real_gate_definition(
    *, gate_id: str = "se.build_tests_pass", severity: Literal["blocking", "warning"] = "blocking"
) -> GateDefinition:
    return GateDefinition(
        id=gate_id,
        name="Build Tests Pass",
        version="0.1.0",
        description="All unit tests pass with zero failures.",
        entrypoint="ai_os_pack_software_engineering.agents.verification:TestAgentEntrypoint",
        type="automated",
        severity=severity,
        success_criteria="The source step's own real `passed` field is `True`.",
        timeout_seconds=None,
        pack_id="software-engineering",
    )


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

    async def list_startable_instances(self, *, limit: int) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")

    async def transition_to_running(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        raise NotImplementedError("not exercised by these tests")

    async def advance_workflow(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def reset_current_step(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def mark_waiting_for_human(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def cancel(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def mark_failed(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def step_failure_stats(self, **kwargs: Any) -> tuple[int, datetime | None]:
        raise NotImplementedError("not exercised by these tests")

    async def record_failed_attempt(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def list_events(self, workflow_id: str) -> list[WorkflowEventRecord]:
        raise NotImplementedError("not exercised by these tests")

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        raise NotImplementedError("not exercised by these tests")

    async def list_runnable_instances(
        self, *, limit: int, exclude_definition_ids: frozenset[str] = frozenset()
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


@pytest.mark.asyncio
async def test_a_registry_resolved_gate_reports_its_real_id_and_version_on_a_pass() -> None:
    # P02-S06-M15-T09's own real proof: the pass/fail decision itself
    # is untouched (still the identical source_output check below) --
    # only the real gateId/gateVersion in the output changes, genuinely
    # resolved through the real Gate Registry, not fabricated.
    repository = _FakeRepository([_step_record(step_name="test", outputs={"passed": True})])
    registry = InMemoryGateRegistry({"se.build_tests_pass": _real_gate_definition()})
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={"quality-gate-tests-pass": "se.build_tests_pass"},
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {
        "gateId": "se.build_tests_pass",
        "gateVersion": "0.1.0",
        "sourceStepId": "test",
        "passed": True,
    }


@pytest.mark.asyncio
async def test_a_registry_resolved_gate_still_blocks_on_a_real_failure() -> None:
    # The real enforcement decision is identical whether or not a
    # registry is wired in -- gate_step_id (used for real retry
    # targeting) stays the workflow-local step id, never the resolved
    # gateId.
    repository = _FakeRepository(
        [_step_record(step_name="test", outputs={"passed": False, "exitCode": 1})]
    )
    registry = InMemoryGateRegistry({"se.build_tests_pass": _real_gate_definition()})
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={"quality-gate-tests-pass": "se.build_tests_pass"},
    )

    with pytest.raises(QualityGateFailedError) as exc_info:
        await executor.execute(_GATE_STEP, workflow_id="wf_fake")
    assert exc_info.value.gate_step_id == "quality-gate-tests-pass"


@pytest.mark.asyncio
async def test_a_resolved_warning_severity_gate_genuinely_records_a_failure_without_blocking() -> (
    None
):
    # P02-S06-M15-T07's own real proof: the Policy Enforcer distinction
    # -- a "warning" gate's own non-passing evaluation returns normally
    # (no exception -- the workflow genuinely proceeds), with a real,
    # honest severity flag in its output, never silently dropped.
    repository = _FakeRepository(
        [_step_record(step_name="test", outputs={"passed": False, "exitCode": 1})]
    )
    registry = InMemoryGateRegistry(
        {"se.build_tests_pass": _real_gate_definition(severity="warning")}
    )
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={"quality-gate-tests-pass": "se.build_tests_pass"},
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {
        "gateId": "se.build_tests_pass",
        "gateVersion": "0.1.0",
        "sourceStepId": "test",
        "passed": False,
        "severity": "warning",
    }


@pytest.mark.asyncio
async def test_a_resolved_warning_severity_gate_still_reports_a_genuine_pass_plainly() -> None:
    repository = _FakeRepository([_step_record(step_name="test", outputs={"passed": True})])
    registry = InMemoryGateRegistry(
        {"se.build_tests_pass": _real_gate_definition(severity="warning")}
    )
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={"quality-gate-tests-pass": "se.build_tests_pass"},
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    # A genuine pass carries no "severity" key regardless of the gate's
    # own declared severity -- identical shape to a passing blocking
    # gate, since severity only ever changes the *failure* consequence.
    assert outputs == {
        "gateId": "se.build_tests_pass",
        "gateVersion": "0.1.0",
        "sourceStepId": "test",
        "passed": True,
    }


@pytest.mark.asyncio
async def test_a_resolved_warning_severity_gate_with_no_persisted_output_yet_does_not_block() -> (
    None
):
    repository = _FakeRepository([_step_record(step_name="test", outputs=None)])
    registry = InMemoryGateRegistry(
        {"se.build_tests_pass": _real_gate_definition(severity="warning")}
    )
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={"quality-gate-tests-pass": "se.build_tests_pass"},
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs["passed"] is False
    assert outputs["severity"] == "warning"


@pytest.mark.asyncio
async def test_a_gate_registry_with_no_matching_gate_ids_entry_falls_back_unchanged() -> None:
    # A registry supplied without a gate_ids mapping for this step is
    # the identical "not configured for this step" shape gate_sources
    # itself already establishes -- real, honest fallback, not an error.
    repository = _FakeRepository([_step_record(step_name="test", outputs={"passed": True})])
    registry = InMemoryGateRegistry({"se.build_tests_pass": _real_gate_definition()})
    executor = QualityGateStepExecutor(
        repository,
        gate_sources={"quality-gate-tests-pass": "test"},
        gate_registry=registry,
        gate_ids={},
    )

    outputs = await executor.execute(_GATE_STEP, workflow_id="wf_fake")

    assert outputs == {"gateId": "quality-gate-tests-pass", "sourceStepId": "test", "passed": True}


class _SleepingGateRegistry:
    """A real `GateRegistry` whose `resolve_gate()` genuinely awaits
    `asyncio.sleep` for a configured duration before returning a real,
    pre-seeded `GateDefinition` — the identical technique
    `test_parallel_step_executor.py`'s own `_SleepingStepExecutor`
    already established, so concurrency is proven by real wall-clock
    timing against a real event loop, never simulated with a registry
    that resolves instantly (which could look "concurrent" by
    accident)."""

    def __init__(self, *, definitions: dict[str, GateDefinition], duration: float) -> None:
        self._definitions = definitions
        self._duration = duration
        self.resolved_gate_ids: list[str] = []

    async def resolve_gate(self, gate_id: str) -> GateDefinition:
        self.resolved_gate_ids.append(gate_id)
        await asyncio.sleep(self._duration)
        try:
            return self._definitions[gate_id]
        except KeyError:
            raise GateNotRegisteredError(f"no gate registered for gateId={gate_id!r}") from None


_MULTI_GATE_STEP = WorkflowStep(id="quality-gate-checks", type=StepType.QUALITY_GATE)


class TestConcurrentMultiGateEvaluation:
    async def test_three_checks_genuinely_resolve_concurrently_not_sequentially(self) -> None:
        # The core proof, mirroring test_parallel_step_executor.py's own
        # technique exactly: three checks, each genuinely resolving in
        # 0.2s, take much less than 3 x 0.2s = 0.6s in total.
        repository = _FakeRepository(
            [
                _step_record(step_name="lint", outputs={"passed": True}),
                _step_record(step_name="test", outputs={"passed": True}),
                _step_record(step_name="scan", outputs={"passed": True}),
            ]
        )
        registry = _SleepingGateRegistry(
            definitions={
                "se.a": _real_gate_definition(gate_id="se.a"),
                "se.b": _real_gate_definition(gate_id="se.b"),
                "se.c": _real_gate_definition(gate_id="se.c"),
            },
            duration=0.2,
        )
        executor = QualityGateStepExecutor(
            repository,
            gate_sources={},
            gate_registry=registry,
            gate_checks={
                "quality-gate-checks": [
                    GateCheck(gate_id="se.a", source_step_id="lint"),
                    GateCheck(gate_id="se.b", source_step_id="test"),
                    GateCheck(gate_id="se.c", source_step_id="scan"),
                ]
            },
        )

        started = time.monotonic()
        outputs = await executor.execute(_MULTI_GATE_STEP, workflow_id="wf_fake")
        elapsed = time.monotonic() - started

        assert elapsed < 0.4  # well under the 0.6s a sequential run would take
        assert elapsed >= 0.2  # sanity: real work genuinely happened
        assert outputs["passed"] is True
        assert {g["gateId"] for g in outputs["gates"]} == {"se.a", "se.b", "se.c"}
        assert all(g["passed"] is True for g in outputs["gates"])

    async def test_any_blocking_failure_blocks_but_every_check_still_ran(self) -> None:
        repository = _FakeRepository(
            [
                _step_record(step_name="lint", outputs={"passed": True}),
                _step_record(step_name="test", outputs={"passed": False, "exitCode": 1}),
            ]
        )
        registry = _SleepingGateRegistry(
            definitions={
                "se.a": _real_gate_definition(gate_id="se.a"),
                "se.b": _real_gate_definition(gate_id="se.b"),
            },
            duration=0.05,
        )
        executor = QualityGateStepExecutor(
            repository,
            gate_sources={},
            gate_registry=registry,
            gate_checks={
                "quality-gate-checks": [
                    GateCheck(gate_id="se.a", source_step_id="lint"),
                    GateCheck(gate_id="se.b", source_step_id="test"),
                ]
            },
        )

        with pytest.raises(QualityGateFailedError) as exc_info:
            await executor.execute(_MULTI_GATE_STEP, workflow_id="wf_fake")

        # Both checks genuinely ran to completion -- a blocking failure
        # never short-circuits the others, the identical "all" policy
        # ParallelStepExecutor already establishes.
        assert sorted(registry.resolved_gate_ids) == ["se.a", "se.b"]
        assert exc_info.value.gate_step_id == "quality-gate-checks"
        assert exc_info.value.results is not None
        by_gate_id = {r["gateId"]: r for r in exc_info.value.results}
        assert by_gate_id["se.a"]["passed"] is True
        assert by_gate_id["se.b"]["passed"] is False

    async def test_a_failing_warning_check_never_blocks_alongside_a_passing_blocking_one(
        self,
    ) -> None:
        repository = _FakeRepository(
            [
                _step_record(step_name="lint", outputs={"passed": True}),
                _step_record(step_name="test", outputs={"passed": False}),
            ]
        )
        registry = _SleepingGateRegistry(
            definitions={
                "se.a": _real_gate_definition(gate_id="se.a", severity="blocking"),
                "se.b": _real_gate_definition(gate_id="se.b", severity="warning"),
            },
            duration=0.01,
        )
        executor = QualityGateStepExecutor(
            repository,
            gate_sources={},
            gate_registry=registry,
            gate_checks={
                "quality-gate-checks": [
                    GateCheck(gate_id="se.a", source_step_id="lint"),
                    GateCheck(gate_id="se.b", source_step_id="test"),
                ]
            },
        )

        outputs = await executor.execute(_MULTI_GATE_STEP, workflow_id="wf_fake")

        assert outputs["passed"] is True
        by_gate_id = {g["gateId"]: g for g in outputs["gates"]}
        assert by_gate_id["se.a"]["passed"] is True
        assert by_gate_id["se.b"]["passed"] is False
        assert by_gate_id["se.b"]["severity"] == "warning"

    async def test_a_step_with_no_workflow_id_is_rejected(self) -> None:
        registry = _SleepingGateRegistry(definitions={}, duration=0.0)
        executor = QualityGateStepExecutor(
            _FakeRepository([]),
            gate_sources={},
            gate_registry=registry,
            gate_checks={"quality-gate-checks": [GateCheck(gate_id="se.a", source_step_id="lint")]},
        )

        with pytest.raises(ValueError, match="requires a real workflow_id"):
            await executor.execute(_MULTI_GATE_STEP)

    async def test_gate_checks_declared_with_no_registry_is_rejected(self) -> None:
        executor = QualityGateStepExecutor(
            _FakeRepository([]),
            gate_sources={},
            gate_checks={"quality-gate-checks": [GateCheck(gate_id="se.a", source_step_id="lint")]},
        )

        with pytest.raises(ValueError, match="no gate_registry"):
            await executor.execute(_MULTI_GATE_STEP, workflow_id="wf_fake")
