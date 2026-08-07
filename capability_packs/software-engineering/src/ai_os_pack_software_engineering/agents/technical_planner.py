"""The Technical Planner Agent — ADR-0021's own sanctioned mechanism
for dynamic decomposition without dynamic control flow: "the
`technical-planner` agent produces a **plan artifact** conforming to a
declared schema. A `foreach` step consumes that artifact and executes
a declared sub-workflow per item." This is this pack's own first
implementation of that plan-artifact schema — `workflows.md`'s own
illustrative pipeline sketches name the field `tasks`
(`implementation_plan.tasks`/`plan.tasks`), reused here rather than
invented.

**A real, disclosed limit, investigated and confirmed before writing
any code (`P03-S02-M29-T08`):** `foreach` is not a real `StepType` —
`ai_os_kernel.workflow_engine.models.StepType` has exactly seven
members (`agent`, `tool`, `decision`, `parallel`, `sub_workflow`,
`quality_gate`, `human_approval`); no `foreach`/`compensate` executor
exists anywhere in the Workflow Engine. This agent produces a real,
schema-validated plan artifact regardless — the identical "build
real, wire later" precedent this session already established
repeatedly in the Evaluation Engine (Metrics Collector, Comparison
Computer, Reporting Interface all shipped real and tested with no
real production caller yet). No workflow anywhere can consume this
agent's own output today; that is a Workflow Engine gap, not a defect
in this agent, and building `foreach` itself is out of this ticket's
own scope (`capability_packs/software-engineering/.../agents`, not
`kernel/.../workflow_engine`).

**Model returns a real JSON array, not this pack's usual
`FILE_PATH`/`FILE_CONTENT_BEGIN` format** — the same departure
`code_review.py` already established for structured, non-file output.
``task_id`` is assigned by this module (``task-1``, ``task-2``, ...
in the model's own returned order), never trusted from the model —
the same "attach structural fields ourselves" principle
`code_review.py` uses for `file`. Fan-out bounding (ADR-0021 point 3:
"`foreach` declares a maximum fan-out") is a `foreach` step's own
declared concern, not this agent's — this module does not cap task
count.

**No `evaluation.llm_calls` capability loss to disclose here** —
SDK-native from its first line, the identical "no migration debt"
note `code_review.py`'s/`database.py`'s own docstrings already make.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut value — the identical "placeholder
# safety limit, not yet tuned" carve-out every agent in this pack
# already uses. Larger than sibling agents' 2048 since a plan may
# legitimately enumerate many tasks.
_MAX_OUTPUT_TOKENS = 4096

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")


class TechnicalPlanInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or the
    model's completion could not be parsed and validated as the
    documented JSON task array. Raised clearly, with the real
    completion text included when parsing fails, never a silent,
    empty task list standing in for a real failure."""


class TechnicalPlanInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). ``design`` always reaches this
    agent via the Context Manager's own assembled ``context`` prompt
    variable — the same real channel `architecture.py`'s own
    ``ArchitectureProposalInput`` documents, one step earlier in the
    pipeline (`workflows.md`: architecture's own design output is
    exactly what a `foreach`-preceding technical-planner step would
    read as ``context``)."""

    design: str = Field(..., description="The technical design to decompose into a plan.")


class PlanTask(BaseModel):
    """One real task in the plan artifact. ``task_id`` is attached by
    this module, never parsed from the model's own response — see
    this module's own docstring."""

    task_id: str = Field(..., alias="taskId")
    title: str
    description: str

    model_config = {"populate_by_name": True}


class _ModelTask(BaseModel):
    """The two fields the model is actually asked for — ``task_id`` is
    deliberately absent; this module attaches it separately."""

    title: str
    description: str


class TechnicalPlanOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs" — the
    real plan artifact ADR-0021 describes. ``tasks`` matches
    `workflows.md`'s own illustrative ``implementation_plan.tasks``/
    ``plan.tasks`` field naming, reused rather than invented."""

    tasks: list[PlanTask]


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "taskId": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["taskId", "title", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tasks"],
    "additionalProperties": False,
}


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mirrors `architecture.py`'s own ``_build_variables`` exactly —
    duck-typed rather than ``isinstance``-checked, for the same reason
    that module's own docstring records."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


def _parse_tasks(completion_text: str) -> list[PlanTask]:
    """Parses and validates the model's own completion as the
    documented JSON task array, assigning each a real, deterministic
    ``task_id`` in the model's own returned order — never trusting one
    out of the model's own response. Raises
    :class:`TechnicalPlanInstructionError` for any failure, with the
    real completion text included."""
    try:
        parsed = json.loads(completion_text)
    except json.JSONDecodeError as exc:
        raise TechnicalPlanInstructionError(
            f"the model's completion was not valid JSON: {exc}\ncompletion: {completion_text}"
        ) from exc

    if not isinstance(parsed, list):
        raise TechnicalPlanInstructionError(
            f"the model's completion was not a JSON array: {completion_text}"
        )

    try:
        model_tasks = [_ModelTask.model_validate(item) for item in parsed]
    except ValidationError as exc:
        raise TechnicalPlanInstructionError(
            f"the model's completion did not match the documented task shape: {exc}\n"
            f"completion: {completion_text}"
        ) from exc

    return [
        PlanTask(
            task_id=f"task-{index + 1}",
            title=model_task.title,
            description=model_task.description,
        )
        for index, model_task in enumerate(model_tasks)
    ]


class TechnicalPlannerAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Technical
    Planner Agent — zero-argument-constructible, the identical shape
    `architecture.py`'s own entrypoint establishes."""

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.llm is None or self._context.prompts is None:
            raise TechnicalPlanInstructionError(
                "TechnicalPlannerAgentEntrypoint.execute() called before bind_pack_context() "
                "bound a PackContext granting the llm:invoke permission "
                "(context.llm/context.prompts) — a real caller must inject one before "
                "first use"
            )

        prompt_id = inputs.get("promptId")
        prompt_version = inputs.get("promptVersion")
        model_alias = inputs.get("modelAlias")
        missing = [
            name
            for name, value in zip(
                _REQUIRED_INVOCATION_FIELDS,
                (prompt_id, prompt_version, model_alias),
                strict=True,
            )
            if not isinstance(value, str) or not value
        ]
        if missing:
            raise TechnicalPlanInstructionError(
                "TechnicalPlannerAgentEntrypoint requires 'promptId', 'promptVersion', "
                f"and 'modelAlias' in its inputs — missing: {', '.join(missing)}"
            )

        rendered = await self._context.prompts.render(
            prompt_id, _build_variables(inputs), version=prompt_version
        )

        workflow_id = inputs.get("workflowId")
        step_id = inputs.get("stepId")
        agent_id = inputs.get("agentId")
        metadata = (
            TraceContext(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex,
                workflow_id=workflow_id,
                step_id=step_id,
                agent_id=agent_id,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )
            if workflow_id is not None or step_id is not None
            else None
        )

        response = await self._context.llm.complete(
            LLMRequest(
                model_alias=model_alias,
                messages=[Message(role=MessageRole.USER, content=rendered.content)],
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                metadata=metadata,
            )
        )
        tasks = _parse_tasks(response.content)

        return {"tasks": [task.model_dump(by_alias=True) for task in tasks]}
