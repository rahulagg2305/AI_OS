"""Unit tests for the real Source Resolvers
(ai_os_kernel.context_manager.resolvers.WorkflowStateResolver,
WorkflowStepOutputResolver) and the shared token-estimate helper — a
fake WorkflowInstanceRepository, no database."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.context_manager.models import ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import (
    WorkflowStateResolver,
    WorkflowStepOutputResolver,
    estimate_tokens,
)
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord


def _instance(inputs: dict[str, Any]) -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id="wf_1",
        definition_id="platform.demo",
        definition_version="1.0.0",
        status=WorkflowInstanceStatus.RUNNING,
        current_step_id="step_1",
        inputs=inputs,
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user-42",
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
    step_name: str,
    outputs: dict[str, Any] | None,
    *,
    attempt: int = 1,
) -> WorkflowStepRecord:
    now = datetime.now(UTC)
    return WorkflowStepRecord(
        step_id=f"step_{step_name}_{attempt}",
        workflow_id="wf_1",
        step_name=step_name,
        step_type=StepType.AGENT,
        status="completed",
        attempt=attempt,
        agent_id="some/agent",
        tool_id=None,
        prompt_id=None,
        prompt_version=None,
        model_alias=None,
        inputs={},
        outputs=outputs,
        error=None,
        idempotency_key=f"wf_1:{step_name}:{attempt}",
        usage={},
        started_at=now,
        completed_at=now,
    )


class _FakeRepository:
    """Returns a fixed instance (or none) for `get_instance`, and a
    fixed list of step records for `list_steps`; every other method is
    unused by these resolvers and raises if called."""

    def __init__(
        self,
        instance: WorkflowInstance | None = None,
        steps: list[WorkflowStepRecord] | None = None,
    ) -> None:
        self._instance = instance
        self._steps = steps or []

    async def create(
        self,
        *,
        definition_id: str,
        definition_version: str,
        inputs: dict[str, Any],
        principal_id: str,
        principal_permissions: frozenset[str] | None = None,
        scheduled_at: datetime | None = None,
    ) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def list_startable_instances(self, *, limit: int) -> list[WorkflowInstance]:
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
        raise NotImplementedError("not exercised by these tests")

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
        raise NotImplementedError("not exercised by these tests")

    async def mark_waiting_for_human(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def cancel(self, **kwargs: Any) -> WorkflowInstance:
        raise NotImplementedError("not exercised by these tests")

    async def record_failed_attempt(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def list_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        return self._steps

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
async def test_resolves_one_item_from_the_instances_own_inputs() -> None:
    resolver = WorkflowStateResolver(_FakeRepository(_instance({"specPath": "specs/x.md"})))

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="step_1"))

    assert len(items) == 1
    assert items[0].provenance.source_type == SourceType.WORKFLOW_STATE
    assert items[0].provenance.identifier == "workflow_instance:wf_1"
    assert items[0].trust == "untrusted"
    assert items[0].relevance_score == 1.0
    assert "specPath" in items[0].content
    assert "specs/x.md" in items[0].content


@pytest.mark.asyncio
async def test_serialises_inputs_deterministically_regardless_of_key_order() -> None:
    # ADR-0022: "context assembly ... is deterministic given the same
    # inputs" — sorted-key serialisation proves key insertion order
    # does not change the assembled content.
    resolver_a = WorkflowStateResolver(_FakeRepository(_instance({"b": 1, "a": 2})))
    resolver_b = WorkflowStateResolver(_FakeRepository(_instance({"a": 2, "b": 1})))
    request = ContextRequest(workflow_id="wf_1", step_id="step_1")

    items_a = await resolver_a.resolve(request)
    items_b = await resolver_b.resolve(request)

    assert items_a[0].content == items_b[0].content


@pytest.mark.asyncio
async def test_returns_no_items_when_the_instance_has_no_inputs() -> None:
    resolver = WorkflowStateResolver(_FakeRepository(_instance({})))

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="step_1"))

    assert items == []


@pytest.mark.asyncio
async def test_returns_no_items_when_the_instance_cannot_be_found() -> None:
    resolver = WorkflowStateResolver(_FakeRepository(None))

    items = await resolver.resolve(ContextRequest(workflow_id="wf_missing", step_id="step_1"))

    assert items == []


def test_estimate_tokens_is_a_deterministic_length_heuristic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 40) == 10


def test_estimate_tokens_never_returns_zero_for_non_empty_content() -> None:
    assert estimate_tokens("ab") == 1


@pytest.mark.asyncio
async def test_step_output_resolver_returns_the_whole_source_step_output_as_json() -> None:
    repository = _FakeRepository(
        steps=[_step_record("build", {"workingDirectory": "workspace", "filePath": "a.py"})]
    )
    resolver = WorkflowStepOutputResolver(repository, step_sources={"test": "build"})

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="test"))

    assert len(items) == 1
    assert items[0].provenance.source_type == SourceType.WORKFLOW_STATE
    assert items[0].provenance.identifier == "workflow_step_output:wf_1:build"
    assert items[0].trust == "untrusted"
    assert "workingDirectory" in items[0].content
    assert "workspace" in items[0].content
    assert "a.py" in items[0].content


@pytest.mark.asyncio
async def test_step_output_resolver_extracts_one_named_field_as_plain_text() -> None:
    repository = _FakeRepository(steps=[_step_record("architecture", {"content": "the design"})])
    resolver = WorkflowStepOutputResolver(
        repository, step_sources={"build": "architecture"}, field_selectors={"build": "content"}
    )

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="build"))

    assert items[0].content == "the design"


@pytest.mark.asyncio
async def test_step_output_resolver_merges_multiple_source_steps_later_wins_on_collision() -> None:
    repository = _FakeRepository(
        steps=[
            _step_record("build", {"filePath": "a.py", "exitCode": 0}),
            _step_record("test", {"passed": True, "exitCode": 1}),
        ]
    )
    resolver = WorkflowStepOutputResolver(
        repository, step_sources={"documentation": ["build", "test"]}
    )

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="documentation"))

    payload = json.loads(items[0].content)
    assert payload["filePath"] == "a.py"
    assert payload["passed"] is True
    assert payload["exitCode"] == 1  # test's own value wins over build's


@pytest.mark.asyncio
async def test_step_output_resolver_applies_an_output_transform_before_encoding() -> None:
    def _add_run_command(output: dict[str, Any]) -> dict[str, Any]:
        return {**output, "runCommand": ["python", output["filePath"]]}

    repository = _FakeRepository(steps=[_step_record("build", {"filePath": "a.py"})])
    resolver = WorkflowStepOutputResolver(
        repository,
        step_sources={"test": "build"},
        output_transforms={"test": _add_run_command},
    )

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="test"))

    payload = json.loads(items[0].content)
    assert payload["runCommand"] == ["python", "a.py"]


@pytest.mark.asyncio
async def test_step_output_resolver_returns_no_items_for_a_step_absent_from_step_sources() -> None:
    repository = _FakeRepository(steps=[_step_record("build", {"filePath": "a.py"})])
    resolver = WorkflowStepOutputResolver(repository, step_sources={"test": "build"})

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="architecture"))

    assert items == []


@pytest.mark.asyncio
async def test_step_output_resolver_returns_no_items_when_the_source_step_has_not_completed() -> (
    None
):
    repository = _FakeRepository(steps=[])
    resolver = WorkflowStepOutputResolver(repository, step_sources={"test": "build"})

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="test"))

    assert items == []


@pytest.mark.asyncio
async def test_step_output_resolver_returns_no_items_when_only_one_source_is_ready() -> None:
    repository = _FakeRepository(steps=[_step_record("build", {"filePath": "a.py"})])
    resolver = WorkflowStepOutputResolver(
        repository, step_sources={"documentation": ["build", "test"]}
    )

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="documentation"))

    assert items == []


@pytest.mark.asyncio
async def test_step_output_resolver_picks_the_highest_attempt_for_a_source_step() -> None:
    repository = _FakeRepository(
        steps=[
            _step_record("build", {"filePath": "first.py"}, attempt=1),
            _step_record("build", {"filePath": "second.py"}, attempt=2),
        ]
    )
    resolver = WorkflowStepOutputResolver(repository, step_sources={"test": "build"})

    items = await resolver.resolve(ContextRequest(workflow_id="wf_1", step_id="test"))

    payload = json.loads(items[0].content)
    assert payload["filePath"] == "second.py"
