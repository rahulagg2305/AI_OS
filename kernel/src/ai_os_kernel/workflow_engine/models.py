"""The Workflow Definition model — in-memory, validated, immutable.

Field-for-field mirror of the **Workflow Contract**
(docs/03_architecture/workflow/workflow_architecture.md, "Workflow
Contract (Mandatory)"), the **Quality Gate Contract** and **Human
Approval Point Contract** referenced from it, and the concurrency rules
in docs/03_architecture/kernel/workflow_engine.md §7.1.

Two deliberate scoping decisions, not omissions:

- ``qualityGates`` is a list of gate-ID references, not inline gate
  definitions — mirroring the already-authoritative
  ``platform_sdk/schemas/manifest.schema.json`` ``agents[].qualityGates``
  shape (full gate definitions are owned by the pack manifest and
  referenced by id everywhere else).
- ``joinPolicy`` (mandatory for a ``parallel`` step,
  ``workflow_engine.md`` §7.1), the five invocation fields below, and —
  as of ``P02-S01-M05-T09``/``P02-S01-M05-T10`` — ``condition``/
  ``branches`` (mandatory for a ``decision`` step; see
  :class:`DecisionCondition`'s own docstring) and ``parallelSteps``
  (mandatory alongside ``joinPolicy`` for a ``parallel`` step — at
  least two nested ``agent``/``tool`` branches) are the per-step fields
  validated here. **Sub-workflow linkage remains genuinely
  undocumented** — no document defines a field-level contract for it
  yet — and stays deferred; inventing one here would still be
  architecture this module does not own. Decision-step branching and
  parallel-step membership are no longer in that category: no document
  defined either, but the product owner explicitly approved a minimal,
  closed-vocabulary contract for each as part of its own step rather
  than leaving the ticket blocked, disclosed as a real, deliberate
  departure from "wait for a document," not an unreviewed invention.

``WorkflowStep``'s five invocation fields (``agentId``, ``toolId``,
``promptId``, ``promptVersion``, ``modelAlias``) are a field-for-field
mirror of the **Step Contract (Minimum Invocation Fields)**
(``workflow_architecture.md``, added directly after "Supported Step
Types") — the same "no document, no field" discipline that already
applied to every other step-payload field before that section existed.
Validated per that section's own five rules exactly:

1. ``type`` remains the sole discriminator — these fields never change
   which executor a step runs through.
2. An ``agent`` step must declare ``agentId``; ``promptId``,
   ``promptVersion``, and ``modelAlias`` are optional on an ``agent``
   step and forbidden on every other step type.
3. A ``tool`` step must declare ``toolId``; ``agentId`` is forbidden on
   a ``tool`` step, the same as on every step type other than ``agent``.
4. Every other step type (``decision``, ``parallel``, ``sub_workflow``,
   ``quality_gate``, ``human_approval``) declares none of these five
   fields.
5. ``promptId``/``promptVersion`` must be declared together or not at
   all — the Prompt Engine's render contract
   (:class:`ai_os_kernel.prompt_engine.models.PromptRenderRequest`)
   requires both, so a step that named only one could never actually
   render anything.

This is a **model/validation-only change**. Nothing here resolves
``agentId``/``toolId`` to a real ``Agent``/``Tool`` instance, calls the
Prompt Engine, or calls the LLM Gateway — ``DispatchingStepExecutor``
continues to invoke the same ``EchoAgent``/``EchoTool`` regardless of
what a step declares (that needs a real Capability Manager registry,
Stage C, a distinct and much larger step). This step only makes the
declared values loadable and validated, closing the gap between
"documented" and "the loader will accept it."
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

# Mirrors platform_sdk/schemas/manifest.schema.json `workflows[].id` —
# dot-namespaced lower snake, the documented convention for workflow,
# tool, gate, and prompt IDs (manifest_schema.md validation rule 4).
_ID_PATTERN = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)*$"

# Mirrors platform_sdk/schemas/manifest.schema.json `workflows[].version`.
_VERSION_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"


class _CamelModel(BaseModel):
    """Base for definition-file models: camelCase on disk, snake_case in
    Python, and no undeclared fields — an unrecognised key fails loudly
    rather than being silently ignored (matches the Manifest Loader's
    strictness)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class StepType(StrEnum):
    """The seven Supported Step Types (workflow_architecture.md)."""

    AGENT = "agent"
    TOOL = "tool"
    DECISION = "decision"
    PARALLEL = "parallel"
    SUB_WORKFLOW = "sub_workflow"
    QUALITY_GATE = "quality_gate"
    HUMAN_APPROVAL = "human_approval"


class JoinPolicy(StrEnum):
    """Mandatory for a ``parallel`` step (workflow_engine.md §7.1)."""

    ALL = "all"
    ANY = "any"
    COLLECT = "collect"


class DecisionCondition(_CamelModel):
    """A ``decision`` step's real, statically-declared condition —
    genuinely evaluated at runtime against a named prior step's own
    recorded output, not an expression language (``P02-S01-M05-T09``,
    closing the gap this module's own docstring used to record: "no
    document defines a field-level contract for [decision-step
    branching] yet"). Kept deliberately narrow, matching the Step
    Contract's own stated design principle for the whole file
    (workflow_architecture.md: "not a general orchestration language"):
    one named source step, one field of its output, one literal
    equality comparison — never a computed expression, template, or
    arbitrary code.
    """

    source_step_id: str
    field: str
    equals: str | int | float | bool | None


class WorkflowStep(_CamelModel):
    """One entry in the workflow's declared step sequence."""

    id: str
    type: StepType
    join_policy: JoinPolicy | None = None
    agent_id: str | None = None
    tool_id: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    model_alias: str | None = None
    condition: DecisionCondition | None = None
    branches: dict[str, str] | None = None
    parallel_steps: list[WorkflowStep] | None = None

    @field_validator("agent_id", "tool_id", "prompt_id", "prompt_version", "model_alias")
    @classmethod
    def _invocation_fields_are_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank when declared")
        return value

    @model_validator(mode="after")
    def _parallel_step_requires_join_policy_and_branches(self) -> WorkflowStep:
        """``P02-S01-M05-T10``: a ``parallel`` step must declare both
        ``joinPolicy`` (already real) and ``parallelSteps`` (new) — the
        minimal, closed contract the product owner approved in place of
        the undocumented one this module's own history already flagged
        for ``decision``: each entry is a full, nested ``WorkflowStep``
        (reusing this exact model recursively, not a second one),
        restricted to ``agent``/``tool`` only — the only two step types
        with a real, self-contained executor today. No nested
        ``parallel``/``decision``/etc.: those all carry cross-step
        reference semantics (a join policy of their own, a
        ``sourceStepId`` elsewhere in the *outer* sequence) that do not
        resolve inside an isolated concurrent branch, so allowing them
        would silently invite a reference that can never work rather
        than fail loudly at load time.
        """
        if self.type is StepType.PARALLEL:
            if self.join_policy is None:
                raise ValueError(
                    f"step '{self.id}': a parallel step must declare joinPolicy "
                    "(all | any | collect) — it fails validation rather than "
                    "defaulting silently (workflow_engine.md §7.1)"
                )
            if not self.parallel_steps:
                raise ValueError(
                    f"step '{self.id}': a parallel step must declare at least two "
                    "parallelSteps — it fails validation rather than defaulting "
                    "silently"
                )
            if len(self.parallel_steps) < 2:
                raise ValueError(
                    f"step '{self.id}': parallelSteps must declare at least two "
                    "branches — a single branch is not genuinely parallel"
                )
            branch_ids = [branch.id for branch in self.parallel_steps]
            duplicates = {bid for bid in branch_ids if branch_ids.count(bid) > 1}
            if duplicates:
                raise ValueError(
                    f"step '{self.id}': duplicate parallelSteps id(s): {sorted(duplicates)}"
                )
            for branch in self.parallel_steps:
                if branch.type not in (StepType.AGENT, StepType.TOOL):
                    raise ValueError(
                        f"step '{self.id}': parallelSteps entry '{branch.id}' declares "
                        f"type '{branch.type.value}' — only agent/tool branches are "
                        "supported (no nested parallel/decision/etc.)"
                    )
        elif self.parallel_steps is not None:
            raise ValueError(f"step '{self.id}': only a parallel step may declare parallelSteps")
        return self

    @model_validator(mode="after")
    def _decision_step_requires_condition_and_branches(self) -> WorkflowStep:
        """Mirrors :meth:`_parallel_step_requires_join_policy_and_branches` exactly,
        for the new decision-step fields this step adds: both required
        together, on a ``decision`` step only, failing validation rather
        than defaulting silently."""
        if self.type is StepType.DECISION:
            if self.condition is None or self.branches is None:
                raise ValueError(
                    f"step '{self.id}': a decision step must declare both "
                    "condition and branches — it fails validation rather than "
                    "defaulting silently"
                )
            if set(self.branches) != {"true", "false"}:
                raise ValueError(
                    f"step '{self.id}': branches must declare exactly the keys "
                    f"'true' and 'false', got {sorted(self.branches)!r} — a closed, "
                    "two-way vocabulary, not an open switch/case"
                )
        elif self.condition is not None or self.branches is not None:
            raise ValueError(
                f"step '{self.id}': only a decision step may declare condition or branches"
            )
        return self

    @model_validator(mode="after")
    def _invocation_fields_match_step_type(self) -> WorkflowStep:
        if self.type is StepType.AGENT:
            if self.agent_id is None:
                raise ValueError(
                    f"step '{self.id}': an agent step must declare agentId "
                    "(workflow_architecture.md's Step Contract)"
                )
            if self.tool_id is not None:
                raise ValueError(
                    f"step '{self.id}': an agent step must not declare toolId "
                    "(workflow_architecture.md's Step Contract)"
                )
        elif self.type is StepType.TOOL:
            if self.tool_id is None:
                raise ValueError(
                    f"step '{self.id}': a tool step must declare toolId "
                    "(workflow_architecture.md's Step Contract)"
                )
            if any(
                value is not None
                for value in (self.agent_id, self.prompt_id, self.prompt_version, self.model_alias)
            ):
                raise ValueError(
                    f"step '{self.id}': a tool step must not declare agentId, "
                    "promptId, promptVersion, or modelAlias "
                    "(workflow_architecture.md's Step Contract)"
                )
        else:
            if any(
                value is not None
                for value in (
                    self.agent_id,
                    self.tool_id,
                    self.prompt_id,
                    self.prompt_version,
                    self.model_alias,
                )
            ):
                raise ValueError(
                    f"step '{self.id}': a {self.type.value} step must not declare "
                    "agentId, toolId, promptId, promptVersion, or modelAlias "
                    "(workflow_architecture.md's Step Contract)"
                )

        if (self.prompt_id is None) != (self.prompt_version is None):
            raise ValueError(
                f"step '{self.id}': promptId and promptVersion must be declared "
                "together or not at all (workflow_architecture.md's Step Contract)"
            )

        return self


class HumanApprovalPoint(_CamelModel):
    """Full Human Approval Point Contract (human_approval_points.md §4)."""

    id: str
    name: str
    description: str
    context: dict[str, Any]
    options: list[str]
    timeout: float | None = Field(default=None, gt=0)
    escalation_policy: dict[str, Any] | None = None
    channels: list[str] | None = None

    @field_validator("options")
    @classmethod
    def _at_least_one_option(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("humanApprovalPoints entry must declare at least one option")
        return value


class RetryPolicy(_CamelModel):
    """Retries must be bounded by both count and duration — not either
    alone (error_handling_retry.md §4: "Retries must be bounded (maximum
    attempts + maximum duration)")."""

    max_attempts: int = Field(gt=0)
    max_duration_seconds: float = Field(gt=0)


class WorkflowDefinition(_CamelModel):
    """The Workflow Contract, as loaded from one definition file."""

    id: str = Field(pattern=_ID_PATTERN)
    name: str
    description: str
    version: str = Field(pattern=_VERSION_PATTERN)
    trigger: str | None = None
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    steps: list[WorkflowStep]
    agents: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)
    human_approval_points: list[HumanApprovalPoint] = Field(default_factory=list)
    failure_handling: dict[str, Any]
    timeout: float | None = Field(default=None, gt=0)
    retry_policy: RetryPolicy | None = None

    @field_validator("steps")
    @classmethod
    def _at_least_one_step(cls, value: list[WorkflowStep]) -> list[WorkflowStep]:
        if not value:
            raise ValueError("steps must declare at least one step")
        return value

    @field_validator("steps")
    @classmethod
    def _step_ids_are_unique(cls, value: list[WorkflowStep]) -> list[WorkflowStep]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for step in value:
            if step.id in seen:
                duplicates.add(step.id)
            seen.add(step.id)
        if duplicates:
            raise ValueError(f"duplicate step id(s): {sorted(duplicates)}")
        return value

    @field_validator("steps")
    @classmethod
    def _decision_step_references_are_real_and_not_forward(
        cls, value: list[WorkflowStep]
    ) -> list[WorkflowStep]:
        """A decision step's own ``condition.sourceStepId`` and both
        ``branches`` targets must name real, declared steps in this same
        definition — the identical "reject a broken reference at load
        time, not at runtime" discipline the Manifest Loader's own
        semantic rule 16 already established for workflow/step
        references. ``sourceStepId`` must additionally appear *earlier*
        in the declared sequence: a forward reference could never
        resolve (that step cannot have executed, let alone recorded an
        output, by the time this one runs) — rejected here, not
        discovered as a real, confusing runtime failure later.
        """
        index_by_id = {step.id: index for index, step in enumerate(value)}
        for index, step in enumerate(value):
            condition, branches = step.condition, step.branches
            if step.type is not StepType.DECISION or condition is None or branches is None:
                # A decision step with either unset already failed
                # `_decision_step_requires_condition_and_branches` (which
                # runs first, per-step, before this definition-level
                # check ever sees it) — nothing left to validate here.
                continue

            source_index = index_by_id.get(condition.source_step_id)
            if source_index is None:
                raise ValueError(
                    f"step '{step.id}': condition.sourceStepId "
                    f"'{condition.source_step_id}' is not a declared step"
                )
            if source_index >= index:
                raise ValueError(
                    f"step '{step.id}': condition.sourceStepId "
                    f"'{condition.source_step_id}' must be declared earlier "
                    "in the sequence — a decision cannot depend on a step that "
                    "has not run yet"
                )

            for outcome, target_id in branches.items():
                if target_id not in index_by_id:
                    raise ValueError(
                        f"step '{step.id}': branches[{outcome!r}] '{target_id}' "
                        "is not a declared step"
                    )
        return value

    @field_validator("inputs", "outputs")
    @classmethod
    def _schema_is_well_formed_json_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"not a well-formed JSON Schema document: {exc.message}") from exc
        return value

    @field_validator("quality_gates")
    @classmethod
    def _quality_gate_references_are_well_formed(cls, value: list[str]) -> list[str]:
        for gate_id in value:
            if not re.match(_ID_PATTERN, gate_id):
                raise ValueError(
                    f"qualityGates reference '{gate_id}' is not a valid gate id "
                    "(dot-namespaced lower snake, e.g. 'se.build')"
                )
        return value

    @field_validator("failure_handling")
    @classmethod
    def _failure_handling_is_declared(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("failureHandling must not be empty")
        return value
