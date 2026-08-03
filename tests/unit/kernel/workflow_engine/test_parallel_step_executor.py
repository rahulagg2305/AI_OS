"""Unit tests for ``ParallelStepExecutor`` — real ``asyncio`` concurrency
throughout, against a real event loop (ADR-0004: no database needed
here; the sub-executors are fake Protocol implementations, but the
concurrency itself is genuine, not simulated). ``P02-S01-M05-T10``.

The core proof every test here ultimately serves: branches genuinely run
at the same time (proven by real wall-clock timing, never by call
order alone — a sequential-but-instant fake could look "concurrent" by
accident), and each real join policy (``all``/``any``/``collect``)
behaves exactly as ``workflow_engine.md`` §7.1 documents it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.errors import ParallelStepFailedError
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.step_executor import ParallelStepExecutor


class _SleepingStepExecutor:
    """A real ``StepExecutor`` whose ``execute()`` genuinely awaits
    ``asyncio.sleep`` for a caller-configured, per-step-id duration,
    then either succeeds with a real, distinct output or raises a real,
    configured exception. Used so concurrency is proven by real
    wall-clock timing against a real event loop, never simulated with
    an executor that resolves instantly (which could look "concurrent"
    purely by accident)."""

    def __init__(
        self,
        *,
        durations: dict[str, float],
        outputs: dict[str, dict[str, Any]] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self._durations = durations
        self._outputs = outputs or {}
        self._errors = errors or {}
        self.executed_step_ids: list[str] = []
        self.cancelled_step_ids: list[str] = []

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        self.executed_step_ids.append(step.id)
        try:
            await asyncio.sleep(self._durations.get(step.id, 0.0))
        except asyncio.CancelledError:
            self.cancelled_step_ids.append(step.id)
            raise
        if step.id in self._errors:
            raise self._errors[step.id]
        return self._outputs.get(step.id, {"result": "ok"})


def _parallel_step(*branch_ids: str, join_policy: str) -> WorkflowStep:
    return WorkflowStep.model_validate(
        {
            "id": "fan_out",
            "type": "parallel",
            "joinPolicy": join_policy,
            "parallelSteps": [
                {"id": bid, "type": "agent", "agentId": "se.software_engineering/analyst"}
                for bid in branch_ids
            ],
        }
    )


async def test_branches_genuinely_run_concurrently_not_sequentially() -> None:
    """The core proof: three branches, each genuinely sleeping 0.2s, take
    much less than 3 x 0.2s = 0.6s in total — real concurrency, not a
    sequential loop that happens to call itself "parallel"."""
    executor = _SleepingStepExecutor(durations={"a": 0.2, "b": 0.2, "c": 0.2})
    step = _parallel_step("a", "b", "c", join_policy="all")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    started = time.monotonic()
    result = await parallel_executor.execute(step)
    elapsed = time.monotonic() - started

    assert elapsed < 0.4  # well under the 0.6s a sequential run would take
    assert elapsed >= 0.2  # sanity: real work genuinely happened
    assert {r["branchId"] for r in result["results"]} == {"a", "b", "c"}
    assert all(r["status"] == "completed" for r in result["results"])


async def test_join_policy_all_succeeds_when_every_branch_succeeds() -> None:
    executor = _SleepingStepExecutor(
        durations={"a": 0.01, "b": 0.01},
        outputs={"a": {"value": 1}, "b": {"value": 2}},
    )
    step = _parallel_step("a", "b", join_policy="all")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    result = await parallel_executor.execute(step)

    assert result["joinPolicy"] == "all"
    by_id = {r["branchId"]: r for r in result["results"]}
    assert by_id["a"] == {
        "branchId": "a",
        "status": "completed",
        "outputs": {"value": 1},
        "error": None,
    }
    assert by_id["b"] == {
        "branchId": "b",
        "status": "completed",
        "outputs": {"value": 2},
        "error": None,
    }


async def test_join_policy_all_fails_when_any_branch_fails_but_every_branch_still_ran() -> None:
    """`all`: a branch failure fails the *step*, but genuine concurrency
    already ran every branch to completion before that's decided — the
    failing branch never short-circuits the others."""
    executor = _SleepingStepExecutor(
        durations={"a": 0.05, "b": 0.05}, errors={"a": RuntimeError("branch a blew up")}
    )
    step = _parallel_step("a", "b", join_policy="all")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    with pytest.raises(ParallelStepFailedError) as exc_info:
        await parallel_executor.execute(step)

    assert sorted(executor.executed_step_ids) == ["a", "b"]  # both genuinely ran
    assert exc_info.value.results[0]["branchId"] in ("a", "b")
    failed = next(r for r in exc_info.value.results if r["branchId"] == "a")
    assert failed["status"] == "failed"
    assert failed["error"] == {"type": "RuntimeError", "message": "branch a blew up"}
    succeeded = next(r for r in exc_info.value.results if r["branchId"] == "b")
    assert succeeded["status"] == "completed"


async def test_join_policy_any_returns_the_first_success_and_genuinely_cancels_the_rest() -> None:
    """`any`: a fast-succeeding branch wins; the slow branches are
    genuinely cancelled, not merely ignored — proven by real elapsed
    time staying close to the fast branch's own duration, nowhere near
    the slow branches'."""
    executor = _SleepingStepExecutor(durations={"fast": 0.02, "slow1": 5.0, "slow2": 5.0})
    step = _parallel_step("fast", "slow1", "slow2", join_policy="any")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    started = time.monotonic()
    result = await parallel_executor.execute(step)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5  # nowhere near the 5s the slow branches would take
    by_id = {r["branchId"]: r for r in result["results"]}
    assert by_id["fast"]["status"] == "completed"
    assert by_id["slow1"]["status"] == "cancelled"
    assert by_id["slow2"]["status"] == "cancelled"
    assert set(executor.cancelled_step_ids) == {"slow1", "slow2"}


async def test_join_policy_any_fails_when_every_branch_fails() -> None:
    executor = _SleepingStepExecutor(
        durations={"a": 0.01, "b": 0.01},
        errors={"a": RuntimeError("a failed"), "b": RuntimeError("b failed")},
    )
    step = _parallel_step("a", "b", join_policy="any")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    with pytest.raises(ParallelStepFailedError, match="every branch failed"):
        await parallel_executor.execute(step)


async def test_join_policy_collect_returns_partial_results_without_raising() -> None:
    """`collect`: the one policy where a failed branch does not fail the
    step — every branch's own real outcome, success or failure, comes
    back as a genuine partial result."""
    executor = _SleepingStepExecutor(
        durations={"a": 0.01, "b": 0.01, "c": 0.01},
        outputs={"a": {"value": 1}},
        errors={"b": RuntimeError("b failed")},
    )
    step = _parallel_step("a", "b", "c", join_policy="collect")
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)

    result = await parallel_executor.execute(step)

    assert result["joinPolicy"] == "collect"
    by_id = {r["branchId"]: r for r in result["results"]}
    assert by_id["a"]["status"] == "completed"
    assert by_id["a"]["outputs"] == {"value": 1}
    assert by_id["b"]["status"] == "failed"
    assert by_id["b"]["error"] == {"type": "RuntimeError", "message": "b failed"}
    assert by_id["c"]["status"] == "completed"


async def test_a_tool_branch_dispatches_to_the_tool_executor_not_the_agent_one() -> None:
    agent_calls: list[str] = []
    tool_calls: list[str] = []

    class _RecordingExecutor:
        def __init__(self, calls: list[str]) -> None:
            self._calls = calls

        async def execute(
            self,
            step: WorkflowStep,
            *,
            workflow_id: str | None = None,
            principal_permissions: frozenset[str] | None = None,
        ) -> dict[str, Any]:
            self._calls.append(step.id)
            return {"ranAs": step.type.value}

    step = WorkflowStep.model_validate(
        {
            "id": "fan_out",
            "type": "parallel",
            "joinPolicy": "all",
            "parallelSteps": [
                {"id": "a", "type": "agent", "agentId": "se.software_engineering/analyst"},
                {"id": "b", "type": "tool", "toolId": "se.build"},
            ],
        }
    )
    parallel_executor = ParallelStepExecutor(
        agent_executor=_RecordingExecutor(agent_calls), tool_executor=_RecordingExecutor(tool_calls)
    )

    await parallel_executor.execute(step)

    assert agent_calls == ["a"]
    assert tool_calls == ["b"]


async def test_rejects_a_non_parallel_step() -> None:
    executor = _SleepingStepExecutor(durations={})
    parallel_executor = ParallelStepExecutor(agent_executor=executor, tool_executor=executor)
    not_parallel = WorkflowStep(
        id="analyze", type=StepType.AGENT, agent_id="se.software_engineering/analyst"
    )

    with pytest.raises(ValueError, match="only handles parallel steps"):
        await parallel_executor.execute(not_parallel)
