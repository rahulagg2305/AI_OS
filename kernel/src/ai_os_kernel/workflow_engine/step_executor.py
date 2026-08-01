"""The seam through which the Workflow Engine invokes a step's real
work (Agent, Tool, Decision, Parallel, Sub-workflow, Quality Gate, Human
Approval — workflow_architecture.md "Supported Step Types").

``NoOpStepExecutor`` always succeeds and does nothing — still the only
implementation for Sub-workflow/Human-Approval steps at this stage.
``AgentStepExecutor`` resolves a step's declared ``agentId`` through an
injected
:class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry` and
invokes the *specific* real (trivial) in-process
:class:`~ai_os_kernel.workflow_engine.agent.Agent` it resolves to;
``ToolStepExecutor`` does the identical thing for ``toolId`` via
:class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry` — both
validate their output. :class:`~ai_os_kernel.workflow_engine.
quality_gate.QualityGateStepExecutor` (added 2026-07-30) is the first
real, non-no-op implementation for a Quality-Gate step — see that
module's own docstring; a caller that does not supply one still routes
``quality_gate`` steps to ``NoOpStepExecutor``, unchanged.
:class:`DecisionStepExecutor` (``P02-S01-M05-T09``) is the real
implementation for a Decision step, genuinely branching subsequent
execution — see its own docstring and
:mod:`ai_os_kernel.workflow_engine.models`'s ``DecisionCondition``.
:class:`ParallelStepExecutor` (``P02-S01-M05-T10``) is the real
implementation for a Parallel step, genuinely running its declared
``parallelSteps`` concurrently via ``asyncio.gather``/``asyncio.wait``
and joining per ``joinPolicy`` — see its own docstring. A caller that
does not supply one still routes ``decision``/``parallel`` steps to
``NoOpStepExecutor``, unchanged. ``DispatchingStepExecutor`` routes
between all six by ``step.type`` — the composition root wires each
individually (ADR-0004: interface-driven; ADR-0010: no DI container).

**Real dispatch by declared id, not real capability discovery.** The
registry each executor is handed may still only contain
``EchoAgent``/``EchoTool`` instances, or now, for agents, a real
:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`,
and for tools, a real :class:`~ai_os_kernel.workflow_engine.
sandboxed_tool.SandboxedCommandTool` — nothing here builds a Capability
Manager, pack activation, or permissions; see :mod:`ai_os_kernel.
workflow_engine.registry` for exactly what is and is not in scope. Real
external tool execution now exists for tools genuinely backed by a
:class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` (see
``ToolStepExecutor`` below); a Tool Invoker component, a Capability
Pack, and a real container-backed sandbox all remain out of scope.

**``StepExecutor.execute`` now also takes an optional ``workflow_id``
keyword** — the Context Manager's own first real slice needs to know
*which instance's* state to read (:class:`~ai_os_kernel.context_manager.
models.ContextRequest` requires it), and a step's own declaration
(``WorkflowStep``, shared across every instance of a workflow) has no
instance identity to give it. Defaulted to ``None`` so every existing
call site, test double, and implementation that never supplies it is
byte-for-byte unaffected — the same "optional, defaulted, zero
behaviour change" shape already established for ``circuit_breaker``/
``budget_enforcer`` on :class:`~ai_os_kernel.llm_gateway.gateway.
DispatchingLLMGateway`. Only :class:`AgentStepExecutor` uses it (agent
steps are the only ones agent_architecture.md documents context
assembly for — see its own docstring below); ``NoOpStepExecutor``,
``ToolStepExecutor``, and ``DispatchingStepExecutor`` accept and
forward it purely for ``Protocol`` uniformity.
"""

import asyncio
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from ai_os_kernel.context_manager.manager import ContextManager
from ai_os_kernel.context_manager.models import ContextRequest
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.errors import (
    AgentOutputValidationError,
    DecisionConditionError,
    ParallelStepFailedError,
    ToolOutputValidationError,
    ToolSandboxRequiredError,
)
from ai_os_kernel.workflow_engine.models import JoinPolicy, StepType, WorkflowStep
from ai_os_kernel.workflow_engine.quality_gate import _latest_completed_output
from ai_os_kernel.workflow_engine.registry import AgentRegistry, ToolRegistry
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository
from ai_os_kernel.workflow_engine.tool import SandboxBackedTool, Tool, TrustTier


class StepExecutor(Protocol):
    """Executes one step and returns its outputs. A real implementation
    raises on failure; this stage only has a stub that always
    succeeds, plus one real (trivial) agent path and one real (trivial)
    tool path."""

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]: ...


class NoOpStepExecutor:
    """Always succeeds immediately with empty outputs. Stands in for a
    real executor until every step type has one (Stage C)."""

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        return {}


class AgentStepExecutor:
    """Resolves the step's declared ``agentId`` through ``registry`` and
    invokes the resulting agent for an Agent-type step, validating its
    output against that agent's declared ``output_schema``.

    Passes the step's declared ``promptId``/``promptVersion``/
    ``modelAlias`` through as ``inputs`` — nothing more, still. This is
    not a per-step input-mapping mechanism: these three fields are the
    only ones workflow_architecture.md's Step Contract documents for an
    agent step, and agent_architecture.md is explicit that "the
    Workflow Engine passes them through without acting on them itself"
    — this executor does not read, validate, or interpret their
    values, it only forwards whichever of the three the step declared
    (all three are optional on `WorkflowStep`; a step declaring none of
    them still executes with an otherwise-empty ``inputs`` dict, exactly
    as before this changed — see :mod:`ai_os_kernel.workflow_engine.agent`
    for :class:`~ai_os_kernel.workflow_engine.agent.EchoAgent`, which
    still ignores whatever it receives).

    **Context assembly is no longer out of scope.** When constructed
    with a real ``context_manager`` *and* called with a real
    ``workflow_id``, this executor now also asks the Context Manager to
    assemble context for this step (agent_architecture.md's Invocation
    Lifecycle, step 1: "Workflow Engine assembles context via the
    Context Manager") and adds the result to ``inputs`` under the
    ``"context"`` key, alongside the three invocation fields — an
    :class:`~ai_os_kernel.context_manager.models.AssembledContext`
    object, passed through structurally, not flattened here (flattening
    into named prompt-template variables is the *consuming* agent's own
    "Context Consumer" job — see :mod:`ai_os_kernel.workflow_engine.
    prompted_agent`). Both ``context_manager`` (defaulted ``None``) and
    ``workflow_id`` (defaulted ``None`` on ``execute`` itself) must be
    present for this to happen — every existing caller/test that
    supplies neither gets byte-for-byte the same ``inputs`` dict as
    before this step.
    """

    def __init__(
        self, registry: AgentRegistry, context_manager: ContextManager | None = None
    ) -> None:
        self._registry = registry
        self._context_manager = context_manager

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is not StepType.AGENT:
            raise ValueError(
                f"AgentStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles agent steps"
            )
        if step.agent_id is None:
            raise ValueError(
                f"step '{step.id}' declares no agentId — WorkflowStep validation "
                "should already have required one for an agent step"
            )
        agent = await self._registry.resolve_agent(step.agent_id)
        inputs = await self._invocation_inputs(step, workflow_id)
        outputs = await agent.execute(inputs)
        self._validate_output(agent, outputs)
        return outputs

    async def _invocation_inputs(
        self, step: WorkflowStep, workflow_id: str | None
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        if step.prompt_id is not None:
            inputs["promptId"] = step.prompt_id
        if step.prompt_version is not None:
            inputs["promptVersion"] = step.prompt_version
        if step.model_alias is not None:
            inputs["modelAlias"] = step.model_alias
        if self._context_manager is not None and workflow_id is not None:
            inputs["context"] = await self._context_manager.assemble(
                ContextRequest(workflow_id=workflow_id, step_id=step.id, agent_id=step.agent_id)
            )
        return inputs

    @staticmethod
    def _validate_output(agent: Agent, outputs: dict[str, Any]) -> None:
        validator = Draft202012Validator(agent.output_schema)
        errors = sorted(validator.iter_errors(outputs), key=lambda e: list(map(str, e.path)))
        if errors:
            lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
            raise AgentOutputValidationError(
                "agent output does not satisfy its declared output_schema:\n" + "\n".join(lines)
            )


class ToolStepExecutor:
    """Resolves the step's declared ``toolId`` through ``registry`` and
    invokes the resulting tool for a Tool-type step, validating its
    output against that tool's declared ``output_schema``.

    A ``tier2_trusted`` tool always runs. A ``tier1_sandboxed`` tool
    runs only when it is genuinely backed by a real
    :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` —
    structurally, :class:`~ai_os_kernel.workflow_engine.tool.SandboxBackedTool`
    — and is refused outright (:class:`ToolSandboxRequiredError`)
    otherwise. This is a narrowing of the original ADR-0016 guard (which
    refused every ``tier1_sandboxed`` tool, since no sandbox existed at
    all), not a relaxation of it: a tool that merely *declares*
    ``tier1_sandboxed`` without a real sandbox behind it is still
    refused, exactly as before. Always invokes with no inputs, for the
    same reason as :class:`AgentStepExecutor`: no per-step input-mapping
    mechanism exists yet; see :mod:`ai_os_kernel.workflow_engine.tool`.
    Accepts ``workflow_id`` for ``StepExecutor`` ``Protocol`` uniformity
    only and never uses it — context_manager.md documents context
    assembly for Agents, not Tools ("a trivial in-process unit of work"
    per workflow_architecture.md's own Step Contract, with no prompt or
    LLM involvement to supply context to).
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is not StepType.TOOL:
            raise ValueError(
                f"ToolStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles tool steps"
            )
        if step.tool_id is None:
            raise ValueError(
                f"step '{step.id}' declares no toolId — WorkflowStep validation "
                "should already have required one for a tool step"
            )
        tool = await self._registry.resolve_tool(step.tool_id)
        if tool.trust_tier is TrustTier.TIER1_SANDBOXED:
            is_sandbox_backed = isinstance(tool, SandboxBackedTool) and tool.sandbox is not None
            if not is_sandbox_backed:
                raise ToolSandboxRequiredError(
                    f"tool for step '{step.id}' declares trust_tier="
                    f"'{tool.trust_tier.value}' but is not genuinely backed by a "
                    "real SandboxExecutor (ADR-0016) — a tier1_sandboxed tool must "
                    "expose a real, working `sandbox` attribute to be dispatched"
                )
        outputs = await tool.execute({})
        self._validate_output(tool, outputs)
        return outputs

    @staticmethod
    def _validate_output(tool: Tool, outputs: dict[str, Any]) -> None:
        validator = Draft202012Validator(tool.output_schema)
        errors = sorted(validator.iter_errors(outputs), key=lambda e: list(map(str, e.path)))
        if errors:
            lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
            raise ToolOutputValidationError(
                "tool output does not satisfy its declared output_schema:\n" + "\n".join(lines)
            )


class DecisionStepExecutor:
    """Executes a ``decision``-type step by genuinely evaluating its
    declared ``condition`` against a named prior step's own real,
    persisted output, and resolving to one of its two declared
    ``branches`` (``P02-S01-M05-T09``, closing the last of the four step
    types this module's own docstring used to list as always
    ``NoOpStepExecutor``-handled, alongside ``QualityGateStepExecutor``
    for ``quality_gate``).

    Reuses :func:`~ai_os_kernel.workflow_engine.quality_gate.
    _latest_completed_output` — the identical "read a named source
    step's own, highest-attempt, real persisted output" logic
    :class:`~ai_os_kernel.workflow_engine.quality_gate.
    QualityGateStepExecutor` already established for the same real
    read model, not a second implementation of it.

    **The real branch outcome is this step's own returned output**
    (``{"outcome": bool, "branch": <resolved step id>}``), persisted the
    identical way every other step's outputs already are —
    :meth:`~ai_os_kernel.workflow_engine.service.
    WorkflowInstanceService._resolve_next_step` reads it back on the
    *next* ``advance()`` call to decide the real next step, rather than
    walking the declared sequence positionally. Nothing here mutates
    control flow directly; it produces the one real fact
    ``_resolve_next_step`` needs to.
    """

    def __init__(self, repository: WorkflowInstanceRepository) -> None:
        self._repository = repository

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is not StepType.DECISION:
            raise ValueError(
                f"DecisionStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles decision steps"
            )
        # Model validation (`_decision_step_requires_condition_and_branches`)
        # already guarantees both are set for a well-formed decision step;
        # narrowed here only so mypy sees it, never a real runtime gap.
        condition, branches = step.condition, step.branches
        if condition is None or branches is None:
            raise ValueError(
                f"step '{step.id}' declares no condition/branches — WorkflowStep "
                "validation should already have required both for a decision step"
            )
        if workflow_id is None:
            raise ValueError(
                f"decision step '{step.id}' requires a real workflow_id to read its "
                "condition's source step output"
            )

        steps = await self._repository.list_steps(workflow_id)
        source_output = _latest_completed_output(steps, condition.source_step_id)
        if source_output is None:
            raise DecisionConditionError(
                f"decision step '{step.id}' could not evaluate its condition: "
                f"source step '{condition.source_step_id}' has no persisted output yet"
            )
        if condition.field not in source_output:
            raise DecisionConditionError(
                f"decision step '{step.id}' could not evaluate its condition: "
                f"source step '{condition.source_step_id}''s output has no field "
                f"'{condition.field}' (real keys: {sorted(source_output)!r})"
            )

        outcome = source_output[condition.field] == condition.equals
        target_step_id = branches["true" if outcome else "false"]
        return {"outcome": outcome, "branch": target_step_id}


class ParallelStepExecutor:
    """Executes a ``parallel``-type step by genuinely running its
    declared ``parallelSteps`` concurrently — real ``asyncio`` tasks,
    not a sequential loop dressed up as parallel — and joining the real
    results per its declared ``joinPolicy`` (``P02-S01-M05-T10``,
    closing the last of the two step types the module docstring used to
    list as always ``NoOpStepExecutor``-handled, alongside
    :class:`DecisionStepExecutor` for ``decision``).

    Each branch is a full, nested ``agent``/``tool`` step (model
    validation already guarantees no other type reaches here), dispatched
    to the same injected ``agent_executor``/``tool_executor`` a real
    workflow-level ``agent``/``tool`` step already uses — no second
    invocation mechanism.

    **Join policies, exactly as ``workflow_engine.md`` §7.1 documents
    them:**

    - ``all`` — every branch must succeed; the step fails
      (:class:`~ai_os_kernel.workflow_engine.errors.
      ParallelStepFailedError`) if *any* branch does, but only after
      every branch has genuinely run to completion (a policy about the
      *outcome*, not early cancellation — ``any`` is where cancellation
      belongs).
    - ``any`` — the first branch to *succeed* wins; every branch still
      running is genuinely cancelled (a real ``asyncio.Task.cancel()``,
      not merely ignored) the moment a success is observed. Only raises
      if every branch fails.
    - ``collect`` — every branch runs to completion; failures are
      reported as real, structured partial results, never raised — the
      one policy where a failed branch does not fail the step.

    Never validates the step's own aggregate output against a declared
    schema — there is no resolved object here (unlike a real ``Agent``/
    ``Tool``) to own one, the identical reasoning
    :class:`DecisionStepExecutor` already established for its own
    output.
    """

    def __init__(self, agent_executor: StepExecutor, tool_executor: StepExecutor) -> None:
        self._agent_executor = agent_executor
        self._tool_executor = tool_executor

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is not StepType.PARALLEL:
            raise ValueError(
                f"ParallelStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles parallel steps"
            )
        branches, join_policy = step.parallel_steps, step.join_policy
        if not branches or join_policy is None:
            raise ValueError(
                f"step '{step.id}' declares no parallelSteps/joinPolicy — "
                "WorkflowStep validation should already have required both for "
                "a parallel step"
            )

        if join_policy is JoinPolicy.ANY:
            results = await self._run_racing_for_first_success(branches, workflow_id=workflow_id)
        else:
            results = await asyncio.gather(
                *(self._run_branch(branch, workflow_id=workflow_id) for branch in branches)
            )

        if join_policy is JoinPolicy.COLLECT:
            return {"joinPolicy": join_policy.value, "results": results}

        failed = [r for r in results if r["status"] == "failed"]
        if join_policy is JoinPolicy.ALL and failed:
            raise ParallelStepFailedError(
                f"parallel step '{step.id}' failed: {len(failed)} of {len(results)} "
                f"branches failed under joinPolicy 'all' "
                f"({[r['branchId'] for r in failed]!r})",
                results=results,
            )
        if join_policy is JoinPolicy.ANY and not any(r["status"] == "completed" for r in results):
            raise ParallelStepFailedError(
                f"parallel step '{step.id}' failed: every branch failed under "
                "joinPolicy 'any' (no branch to declare a winner)",
                results=results,
            )
        return {"joinPolicy": join_policy.value, "results": results}

    async def _run_branch(self, branch: WorkflowStep, *, workflow_id: str | None) -> dict[str, Any]:
        executor = self._agent_executor if branch.type is StepType.AGENT else self._tool_executor
        try:
            outputs = await executor.execute(branch, workflow_id=workflow_id)
            return {"branchId": branch.id, "status": "completed", "outputs": outputs, "error": None}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {
                "branchId": branch.id,
                "status": "failed",
                "outputs": None,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }

    async def _run_racing_for_first_success(
        self, branches: list[WorkflowStep], *, workflow_id: str | None
    ) -> list[dict[str, Any]]:
        """``joinPolicy: any`` — the first genuine success wins; every
        branch still in flight at that moment is really cancelled, not
        merely abandoned. Failed branches observed before a success
        contribute their own real result; a still-running branch that
        gets cancelled is reported as ``"cancelled"``, an honest third
        outcome distinct from ``"completed"``/``"failed"``."""
        tasks = {
            asyncio.ensure_future(self._run_branch(branch, workflow_id=workflow_id)): branch
            for branch in branches
        }
        results: dict[str, dict[str, Any]] = {}
        pending = set(tasks)
        winner_found = False

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result = task.result()
                results[result["branchId"]] = result
                if result["status"] == "completed":
                    winner_found = True
            if winner_found:
                break

        for task in pending:
            branch = tasks[task]
            task.cancel()
            results[branch.id] = {
                "branchId": branch.id,
                "status": "cancelled",
                "outputs": None,
                "error": None,
            }
        # Let cancellation actually propagate through the task before
        # returning — a fire-and-forget cancel() request is not itself
        # proof the branch's own coroutine has genuinely stopped running.
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        return [results[branch.id] for branch in branches]


class DispatchingStepExecutor:
    """Routes an Agent-type step to ``agent_executor``, a Tool-type step
    to ``tool_executor``, a Quality-Gate-type step to
    ``quality_gate_executor`` (when supplied), a Decision-type step to
    ``decision_executor`` (when supplied), a Parallel-type step to
    ``parallel_executor`` (when supplied), and every other step type to
    ``default_executor``.

    The only place that knows all six executors exist; none of them
    needs to know about the others or about step types it does not
    handle. ``quality_gate_executor``/``decision_executor``/
    ``parallel_executor`` all default to ``None`` — every existing
    caller that does not supply one keeps routing that step type to
    ``default_executor`` exactly as before (:class:`NoOpStepExecutor`,
    unchanged); only a caller that genuinely wants real, blocking gate
    evaluation (:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`),
    real decision-step branching, or real concurrent parallel execution
    supplies :class:`~ai_os_kernel.workflow_engine.quality_gate.
    QualityGateStepExecutor`/:class:`DecisionStepExecutor`/
    :class:`ParallelStepExecutor` here.
    """

    def __init__(
        self,
        agent_executor: StepExecutor,
        tool_executor: StepExecutor,
        default_executor: StepExecutor,
        quality_gate_executor: StepExecutor | None = None,
        decision_executor: StepExecutor | None = None,
        parallel_executor: StepExecutor | None = None,
    ) -> None:
        self._agent_executor = agent_executor
        self._tool_executor = tool_executor
        self._default_executor = default_executor
        self._quality_gate_executor = quality_gate_executor
        self._decision_executor = decision_executor
        self._parallel_executor = parallel_executor

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is StepType.AGENT:
            return await self._agent_executor.execute(step, workflow_id=workflow_id)
        if step.type is StepType.TOOL:
            return await self._tool_executor.execute(step, workflow_id=workflow_id)
        if step.type is StepType.QUALITY_GATE and self._quality_gate_executor is not None:
            return await self._quality_gate_executor.execute(step, workflow_id=workflow_id)
        if step.type is StepType.DECISION and self._decision_executor is not None:
            return await self._decision_executor.execute(step, workflow_id=workflow_id)
        if step.type is StepType.PARALLEL and self._parallel_executor is not None:
            return await self._parallel_executor.execute(step, workflow_id=workflow_id)
        return await self._default_executor.execute(step, workflow_id=workflow_id)
