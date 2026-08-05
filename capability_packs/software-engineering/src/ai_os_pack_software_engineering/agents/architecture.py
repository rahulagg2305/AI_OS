"""The Architecture Agent — agent_architecture.md's "Agent Categories
(Initial Target)" #2, this pack's first real increment. Given a
software requirement, proposes a concrete technical design. No code
generation, no Build/Test/Documentation Agents, no approval gating —
output capture only, exactly this step's own approved scope.

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 11) — the second agent needing real gateway injection, following
the exact pattern step 10 (`requirements-analyst`) established.** This
entrypoint now implements :class:`~ai_os_sdk.contracts.Agent` and
:class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
only. It imports nothing from ``ai_os_kernel`` at all: no database
engine, no secret provider, no ``load_provider_config``, no
``build_anthropic_prompted_completion_service``. Where it used to lazily
build its own real :class:`~ai_os_kernel.workflow_engine.prompted_agent.
PromptedAgent` (itself wrapping a real
:class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`) on
first :meth:`execute` call, guarded by an ``asyncio.Lock()``, it now
reads ``self._context.llm``/``self._context.prompts`` — the real
:class:`~ai_os_kernel.sdk_adapters.llm_gateway_adapter.LLMGatewayAdapter`/
:class:`~ai_os_kernel.sdk_adapters.prompt_registry_adapter.
PromptRegistryAdapter` a caller injects via :meth:`bind_pack_context`,
directly replicating :meth:`~ai_os_kernel.prompted_completion.
PromptedCompletionService.complete_from_prompt`'s own real logic
(render, then complete) using only SDK Protocols.

**The lazy-build lock is gone entirely, for the identical reason step 10
already found and recorded — not re-litigated here, only confirmed to
generalize.** ``bind_pack_context()`` is a plain, synchronous method,
called exactly once by the resolver (``SqlAgentRegistry``, as of step
9a) immediately after construction — genuinely before any concurrent
``execute()`` call could possibly begin. There is no race left to guard
against, so the lock and the lazy-build method are simply not present in
this module at all. See ``requirements_analyst.py``'s own docstring, and
``platform_sdk_v1_scope.md`` §6m, for the full reasoning this step
reuses rather than repeats.

**The identical, already-recorded, unavoidable capability loss applies
here too: real Anthropic completions from this agent are no longer
recorded to ``evaluation.llm_calls``.** No new finding — the same gap
step 10 recorded in ``platform_sdk_v1_scope.md`` §6m and
``feature_inventory.md``'s own Platform SDK tracking, now confirmed to
apply to a second migrated agent, not a new discovery.

**``workflow_id``/``step_id`` still reach the real per-workflow budget
ceiling, faithfully, for the identical reason step 10 already
documented** — see ``requirements_analyst.py``'s own docstring for the
full ``TraceContext``-narrowing chain; this module's own trace handling
is a literal copy of that reasoning, not a second, divergent one.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut value, not yet tuned against real
# architecture-proposal output lengths — the same "placeholder safety
# limit" carve-out every agent in this pack already uses.
_MAX_OUTPUT_TOKENS = 2048

# Mirrors PromptedAgent.output_schema exactly — see this module's own
# docstring (pre-migration history) for why this is a literal copy, not
# a derived reference.
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
    "additionalProperties": False,
}

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")


class ArchitectureAgentInputError(ValueError):
    """This agent's inputs were missing a required invocation field
    (``promptId``/``promptVersion``/``modelAlias``) — the same real
    contract :class:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent` already enforced, now enforced directly here since
    this agent no longer delegates to it."""


class ArchitectureProposalInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md) — the manifest's own required
    ``inputSchema`` field names this model. **Not yet validated at
    runtime**: no per-step input-mapping mechanism exists in this
    codebase to check any agent's inputs against a declared schema
    (:mod:`ai_os_kernel.workflow_engine.agent`'s own long-established,
    unchanged scope). ``requirement`` always reaches this agent via the
    Context Manager's own assembled ``context`` prompt variable — the
    one real channel ``AgentStepExecutor`` already establishes; this
    field records the documented contract, not a second, real input
    path. **Which real source populates that variable is a per-workflow
    composition choice, not fixed by this agent.** In
    ``se.delivery_pipeline`` specifically, it is no longer the
    workflow's own raw top-level ``inputs`` — since this pipeline wired
    Requirements Analyst in as its own first step, this agent's
    ``context`` variable is Requirements Analyst's own real, refined
    output (see ``ai_os_kernel.workflow_engine.delivery_pipeline``'s own
    ``_STEP_SOURCES``/``_FIELD_SELECTORS`` for that pipeline's specific
    wiring) — a different, but structurally identical, real source
    supplying the same variable this agent has always read.
    """

    requirement: str = Field(
        ..., description="The software requirement or specification to design for."
    )


class ArchitectureProposalOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs" — free
    text (a design proposal, per this agent's prompt), not a structured
    object."""

    content: str = Field(..., description="The proposed architecture and design, as free text.")


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mirrors :meth:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent._build_variables` exactly, duck-typed rather than
    ``isinstance``-checked against ``AssembledContext`` — see
    ``requirements_analyst.py``'s own docstring and
    ``platform_sdk_v1_scope.md`` §6k for why: the real object the
    Workflow Engine sends here is still Kernel-typed, a different class
    from the SDK's own boundary model, so a nominal check would always
    be ``False`` against it."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class ArchitectureAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Architecture
    Agent — zero-argument-constructible
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
            raise ArchitectureAgentInputError(
                "ArchitectureAgentEntrypoint.execute() called before bind_pack_context() "
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
            raise ArchitectureAgentInputError(
                "ArchitectureAgentEntrypoint requires 'promptId', 'promptVersion', "
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

        return {"content": response.content}
