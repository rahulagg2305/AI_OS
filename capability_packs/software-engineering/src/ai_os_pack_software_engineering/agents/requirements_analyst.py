"""The Requirements Analyst Agent — agents.md's own Agent Catalog #1
(`software-engineering/requirements-analyst`), the natural upstream
predecessor to the Architecture Agent this pack already has: given a
raw software requirement or ask, produce a structured, refined
requirements analysis an Architecture Agent (or a human) can design
against. No code generation, no architecture design, no validation
against acceptance criteria beyond what the model itself states —
output capture only, the identical scope reduction every agent in this
pack has used for its own first real slice.

**Accepts an optional, additive `specification` input (FR-030,
`P03-S03-M30-T02`), on top of the pre-existing, still-required
`requirement`.** Design fork resolved with the product owner before
writing code: additive, not a breaking replace of `requirement` — 13
existing test files/callers across this repo already construct a
trigger payload with only `requirement`, and none of them changes
here. **A real, discovered gap fixed before shipping, not after**: an
earlier draft read ``inputs.get("specification")`` directly and always
got ``None`` in production — ``AgentStepExecutor`` forwards only
``promptId``/``promptVersion``/``modelAlias``/``stepId``/``agentId``/
``workflowId``/``context`` to any agent's own ``execute()``, never
arbitrary ``instance.inputs`` keys (no per-step input-mapping mechanism
exists, confirmed by this module's own long-standing docstring on
:class:`RequirementsAnalysisInput`) — a live, real, Postgres-backed
integration test caught this the deterministic pack-only unit tests
could not, because only the integration test drove a genuine
``AgentStepExecutor``/Context Manager/``WorkflowStateResolver`` chain
rather than a hand-built ``inputs`` dict. The real fix,
:func:`_extract_specification_from_context`: read ``specification``
back out of ``WorkflowStateResolver``'s own existing, unchanged
JSON-dumped ``instance.inputs`` context item — the one real channel
that already, genuinely carries it this far. Once extracted, it is
parsed via :mod:`ai_os_pack_software_engineering.workflows.spec_parser`
(this agent's own first, and today only, real consumer of that module
— the Kernel's own pipeline composition never imports pack code, so
parsing cannot live there) into a real, validated list folded into
this agent's own `context` prompt variable (alongside the same raw
text already embedded once via the JSON dump — a disclosed, harmless
redundancy, not a bug), and returned verbatim as this step's own new
`specificationItems` output field — the literal, provable "parsed,
validated requirement items" `P03-S03-M30-T02` asks for, not merely
inert plumbing. A malformed `specification` (no bullet item found, or
an empty one) fails this step with a clear `RequirementsAnalystInputError`
before any LLM call is made, rather than silently proceeding or
wasting a completion on unusable input.

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 10) — the first agent needing real gateway injection.** This
entrypoint now implements :class:`~ai_os_sdk.contracts.Agent` and
:class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
only. It imports nothing from ``ai_os_kernel`` at all: no database
engine, no secret provider, no ``load_provider_config``, no
``build_anthropic_prompted_completion_service``. Where it used to lazily
build its own real :class:`~ai_os_kernel.workflow_engine.prompted_agent.
PromptedAgent` (itself wrapping a real
:class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`) on
first :meth:`execute` call, it now reads ``self._context.llm``/
``self._context.prompts`` — the real
:class:`~ai_os_kernel.sdk_adapters.llm_gateway_adapter.LLMGatewayAdapter`/
:class:`~ai_os_kernel.sdk_adapters.prompt_registry_adapter.
PromptRegistryAdapter` a caller injects via :meth:`bind_pack_context`,
directly replicating :meth:`~ai_os_kernel.prompted_completion.
PromptedCompletionService.complete_from_prompt`'s own real logic
(render, then complete) using only SDK Protocols.

**The lazy-build lock is gone entirely — not preserved alongside the new
mechanism, and this is the real finding this step's own approved framing
asked to watch for.** ``ArchitectureAgentEntrypoint``'s own docstring
(and this module's own, before this step) explains *why* the lazy-build-
under-an-``asyncio.Lock()`` pattern existed: ``EntrypointLoader`` only
ever calls ``cls()``, so a real, async-composed dependency had nowhere
honest to be built except lazily, on first (necessarily async)
``execute()`` call, guarded against a concurrent double-build. **The
step 6b/9a injection mechanism does not need that guard, and adding one
back would be redundant complexity, not a tension to resolve.**
:meth:`bind_pack_context` is a plain, synchronous method, called exactly
once by the resolver (``SqlAgentRegistry``, as of step 9a) immediately
after construction — genuinely before any concurrent ``execute()`` call
could possibly begin, since nothing can call ``execute()`` on an
instance it has not yet received from ``resolve_agent()``. There is no
race to guard against, because composition moved from "lazily, inside
the object, racing against its own first use" to "eagerly, by the
caller, strictly before any use is possible." The old pattern is not in
tension with the new one; it is simply obsolete for any fully-migrated
agent, and this module no longer carries it.

**A real, discovered, unavoidable capability loss, recorded rather than
silently dropped: real Anthropic completions from this agent are no
longer recorded to ``evaluation.llm_calls``.**
:func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`
always wired a real
:class:`~ai_os_kernel.llm_gateway.call_recorder.SqlLLMCallRecorder` into
the :class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`
this agent used to delegate to — every real completion was recorded.
Platform SDK v1.0.0 has no ``Telemetry``/``TraceabilityService`` surface
at all (both are explicitly deferred past v1.0.0, ``platform_sdk.md``
§2), so there is no SDK-sanctioned way for a migrated agent to preserve
this — reaching back into ``ai_os_kernel.llm_gateway.call_recorder``
directly would reintroduce exactly the forbidden import this migration
removes. This does not change this agent's own visible output (the
``analysis`` this method returns is identical either way) — it is a
real, silent loss of observability data, not a functional regression,
and is recorded here as a concrete input for whichever future step adds
a real ``Telemetry``/call-recording surface to the SDK.

**``workflow_id``/``step_id`` still reach the real per-workflow budget
ceiling, faithfully, even though this agent can no longer build a
Kernel ``TraceContext`` directly.** ``DispatchingLLMGateway``'s own
per-workflow budget enforcement (llm_gateway.md §9) keys off
``workflow_id`` inside the request's own metadata —
:class:`~ai_os_kernel.sdk_adapters.llm_gateway_adapter.LLMGatewayAdapter`'s
own real, already-proven conversion narrows the SDK's 7-field
``TraceContext`` down to the Kernel's own ``workflow_id``/``step_id``-only
one (step 6a's own documented narrowing), so passing them through the
SDK's own model still reaches the real budget enforcer unchanged.
``trace_id``/``span_id`` are required fields on the SDK's own
``TraceContext`` model but are functionally inert once converted (the
Kernel's own narrower shape drops them) — generated fresh, per call,
with the stdlib's own ``uuid.uuid4().hex`` (mirroring, in spirit,
:func:`~ai_os_kernel.observability.trace.generate_trace_id`'s identical
scheme, but implemented here with no ``ai_os_kernel`` import at all,
since this pack module may not have one).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ai_os_pack_software_engineering.workflows.spec_parser import (
    SpecificationParseError,
    parse_markdown_specification,
)
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut value, not yet tuned against real
# requirements-analysis output lengths — the same "placeholder safety
# limit" carve-out every agent in this pack already uses.
_MAX_OUTPUT_TOKENS = 2048

# This agent's own output field is `analysis`, not `content` — see this
# module's own docstring for why. `specificationItems` (added
# `P03-S03-M30-T02`) is optional and omitted entirely unless a caller
# supplied `specification` and it parsed successfully — never `null`.
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string"},
        "specificationItems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["analysis"],
    "additionalProperties": False,
}

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")


class RequirementsAnalystInputError(ValueError):
    """This agent's inputs were missing a required invocation field
    (``promptId``/``promptVersion``/``modelAlias``) — the same real
    contract :class:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent` already enforced, now enforced directly here since
    this agent no longer delegates to it."""


class RequirementsAnalysisInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    the identical, still unchanged "no per-step input-mapping mechanism
    exists" scope every agent in this pack already documents.
    ``requirement`` reaches this agent the same way it reaches the
    Architecture Agent: via the Context Manager's own assembled
    ``context`` prompt variable.
    """

    requirement: str = Field(
        ..., description="The raw software requirement or ask to analyze and refine."
    )
    specification: str | None = Field(
        default=None,
        description=(
            "An optional structured Markdown specification (FR-030, "
            "`P03-S03-M30-T02`) — see "
            "ai_os_pack_software_engineering.workflows.spec_parser's own "
            "docstring for the exact convention. When present, it is "
            "parsed into requirement items and folded into this agent's "
            "own context alongside `requirement`, which is unaffected."
        ),
    )


class RequirementsAnalysisOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs" — free
    text (a structured requirements analysis, per this agent's own
    prompt), not a further-structured object. Named ``analysis``, not
    ``content``, per this module's own docstring. ``specification_items``
    (added `P03-S03-M30-T02`) is the real, parsed, validated list FR-030
    asks for — present only when a caller supplied `specification` and
    it parsed successfully."""

    specification_items: list[str] | None = Field(default=None, alias="specificationItems")

    model_config = {"populate_by_name": True}

    analysis: str = Field(
        ..., description="The refined, structured requirements analysis, as free text."
    )


def _extract_specification_from_context(inputs: dict[str, Any]) -> str | None:
    """Reads the raw ``specification`` instance input back out of the
    one real, existing channel that ever carries it to this step:
    ``WorkflowStateResolver``'s own JSON-dumped ``instance.inputs``
    context item (``ai_os_kernel.context_manager.resolvers``).

    **There is no more direct route, and this is not a workaround —
    it is the honest consequence of two real, pre-existing facts, both
    already documented elsewhere in this module: no per-step
    input-mapping mechanism exists (`AgentStepExecutor` forwards only
    `promptId`/`promptVersion`/`modelAlias`/`stepId`/`agentId`/
    `workflowId`/`context` — never arbitrary `instance.inputs` keys),
    and this pack's own parsing logic cannot live in the Kernel (no
    pack's source is ever imported there — see this module's own
    docstring). `WorkflowStateResolver` already serializes the whole
    `instance.inputs` dict as one JSON-dumped context item scoped to
    this step alone — this function's only job is picking `specification`
    back out of it, duck-typed the same way :func:`_build_variables`
    already reads `context.items`.**"""
    context = inputs.get("context")
    items = getattr(context, "items", None) or []
    for item in items:
        content = getattr(item, "content", None)
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except ValueError:
            continue
        if isinstance(payload, dict):
            candidate = payload.get("specification")
            if isinstance(candidate, str):
                return candidate
    return None


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mirrors :meth:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent._build_variables` exactly, duck-typed rather than
    ``isinstance``-checked against ``AssembledContext`` — see this
    module's own docstring and ``platform_sdk_v1_scope.md`` §6k for why:
    the real object the Workflow Engine sends here is still Kernel-typed,
    a different class from the SDK's own boundary model, so a nominal
    check would always be ``False`` against it."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class RequirementsAnalystAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Requirements
    Analyst Agent — zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`).
    See this module's own docstring for why it no longer lazily builds
    anything: real composition now arrives, once, via
    :meth:`bind_pack_context`.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.llm is None or self._context.prompts is None:
            raise RequirementsAnalystInputError(
                "RequirementsAnalystAgentEntrypoint.execute() called before "
                "bind_pack_context() bound a PackContext granting the llm:invoke "
                "permission (context.llm/context.prompts) — a real caller must "
                "inject one before first use"
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
            raise RequirementsAnalystInputError(
                "RequirementsAnalystAgentEntrypoint requires 'promptId', 'promptVersion', "
                f"and 'modelAlias' in its inputs — missing: {', '.join(missing)}"
            )

        specification = _extract_specification_from_context(inputs)
        specification_items: list[str] | None = None
        if isinstance(specification, str) and specification.strip():
            try:
                specification_items = parse_markdown_specification(specification)
            except SpecificationParseError as exc:
                raise RequirementsAnalystInputError(
                    f"RequirementsAnalystAgentEntrypoint's 'specification' input failed to "
                    f"parse: {exc}"
                ) from exc

        variables = _build_variables(inputs)
        if specification_items is not None:
            items_block = "\n".join(
                f"{index + 1}. {item}" for index, item in enumerate(specification_items)
            )
            existing_context = variables.get("context", "")
            variables["context"] = (
                f"{existing_context}\n\nStructured specification items:\n{items_block}"
                if existing_context
                else f"Structured specification items:\n{items_block}"
            )

        rendered = await self._context.prompts.render(prompt_id, variables, version=prompt_version)

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

        output: dict[str, Any] = {"analysis": response.content}
        if specification_items is not None:
            output["specificationItems"] = specification_items
        return output
