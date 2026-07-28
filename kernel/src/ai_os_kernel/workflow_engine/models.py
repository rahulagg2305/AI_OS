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
  ``workflow_engine.md`` §7.1) and the five invocation fields below are
  the only per-step fields validated here. Decision-step branching and
  sub-workflow linkage remain genuinely undocumented — no document
  defines a field-level contract for them yet — and are still deferred;
  inventing one here would be architecture this module does not own.

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

    @field_validator("agent_id", "tool_id", "prompt_id", "prompt_version", "model_alias")
    @classmethod
    def _invocation_fields_are_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank when declared")
        return value

    @model_validator(mode="after")
    def _parallel_step_requires_join_policy(self) -> WorkflowStep:
        if self.type is StepType.PARALLEL and self.join_policy is None:
            raise ValueError(
                f"step '{self.id}': a parallel step must declare joinPolicy "
                "(all | any | collect) — it fails validation rather than "
                "defaulting silently (workflow_engine.md §7.1)"
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
