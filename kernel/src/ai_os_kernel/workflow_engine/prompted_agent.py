"""The first real, non-``Echo*`` :class:`~ai_os_kernel.workflow_engine.
agent.Agent` implementation — the "wire one thin real Agent" step's own
deliverable.

Realises the invocation lifecycle agent_architecture.md already
documents: "When the invoking workflow step declares ``promptId``/
``promptVersion``/``modelAlias`` ... those are inputs to the agent's own
invocation ... the Workflow Engine passes them through without acting
on them itself." :class:`~ai_os_kernel.workflow_engine.step_executor.
AgentStepExecutor` now does exactly that (see its own docstring) —
:class:`PromptedAgent` is the agent on the other end that actually
*uses* them: it reads the three fields from its ``inputs`` dict,
delegates to the existing :class:`~ai_os_kernel.prompted_completion.
PromptedCompletionService` (unchanged — this step needed no new
composition logic, only a real caller for it), and returns the
completion's text as its structured output.

**Constructor-injected, not entrypoint-loadable, and that is a
deliberate, already-established boundary, not an oversight.**
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
always constructs with zero arguments — its own docstring already
states why: "Passing manifest-declared configuration into an
entrypoint's constructor is real Capability Manager design work, not
attempted here." A real ``PromptedCompletionService`` needs a database
engine, a resolved secret, and model/pricing configuration — genuine
constructor dependencies with nowhere honest to come from inside a
zero-argument ``cls()`` call. This agent is therefore used through
:class:`~ai_os_kernel.workflow_engine.registry.InMemoryAgentRegistry`
(the composition root constructs it once, with its real dependencies,
and hands the instance to the registry) — the identical "existing
registry path" :class:`~ai_os_kernel.workflow_engine.agent.EchoAgent`
itself is already exercised through in the current test suite. Making a
dependency-carrying agent loadable via
:class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`'s real
entrypoint mechanism would require passing it real configuration at
construction time — Capability Manager territory, explicitly out of
scope for this step.

**No new input-mapping system.** ``variables``/``workflowId``/
``stepId``/``agentId`` are read from ``inputs`` too, but only ever as a
direct, unmodified passthrough to
:meth:`~ai_os_kernel.prompted_completion.PromptedCompletionService.complete_from_prompt`'s
own already-existing, already-optional parameters — nothing here
decides what these values *should* be or maps them from anywhere new.
``maxOutputTokens`` is deliberately **not** one of these: it is not part
of the documented Step Contract, so it is a required constructor
parameter instead — configuration the composition root supplies once
per agent instance, not a field this step invents on ``WorkflowStep``.

**This is now also agent_architecture.md's "Context Consumer" — the
first, and so far only, real one.** When
:class:`~ai_os_kernel.workflow_engine.step_executor.AgentStepExecutor`
was constructed with a real Context Manager, ``inputs`` may carry a
``"context"`` key: a real
:class:`~ai_os_kernel.context_manager.models.AssembledContext`. This
agent reads it (never assembles its own — agent_architecture.md: "an
agent **consumes** the ``AssembledContext`` supplied by the Context
Manager and never performs its own retrieval") and flattens its items
into exactly one prompt template variable, ``context`` — a newline-
joined concatenation of every item's ``content``, in the order the
Context Manager returned them. This is a deliberately minimal mapping,
not a general-purpose one: with only one real resolver (Workflow
State) and no ranking, there is nothing yet that would justify mapping
different items to different named variables. An explicit
``variables["context"]`` supplied by a caller still wins — this only
fills a gap, it never overrides an explicit value. When ``inputs`` has
no ``"context"`` key (every caller before this step, and every caller
whose ``AgentStepExecutor`` has no Context Manager configured), this
is a complete no-op — the identical, unaffected `variables` this
method already built.
"""

from __future__ import annotations

from typing import Any, cast

from ai_os_kernel.context_manager.models import AssembledContext
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.errors import PromptedAgentInputError


def _flatten_context(context: AssembledContext) -> str:
    """Concatenates every assembled item's content in resolver order —
    see this module's own docstring for why this is deliberately the
    only mapping strategy implemented so far."""
    return "\n\n".join(item.content for item in context.items)


class PromptedAgent:
    """Delegates entirely to an injected :class:`PromptedCompletionService`.
    No LLM Gateway or Prompt Engine access of its own — those seams
    belong to the service it wraps, exactly as
    :mod:`~ai_os_kernel.workflow_engine.agent`'s own module docstring
    already scopes an ``Agent``'s responsibilities.
    """

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }

    def __init__(self, *, service: PromptedCompletionService, max_output_tokens: int) -> None:
        self._service = service
        self._max_output_tokens = max_output_tokens

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        prompt_id = inputs.get("promptId")
        prompt_version = inputs.get("promptVersion")
        model_alias = inputs.get("modelAlias")
        missing = [
            name
            for name, value in (
                ("promptId", prompt_id),
                ("promptVersion", prompt_version),
                ("modelAlias", model_alias),
            )
            if not isinstance(value, str) or not value
        ]
        if missing:
            raise PromptedAgentInputError(
                "PromptedAgent requires 'promptId', 'promptVersion', and 'modelAlias' in its "
                f"inputs (agent_architecture.md's invocation lifecycle) — missing: "
                f"{', '.join(missing)}"
            )
        result = await self._service.complete_from_prompt(
            prompt_id=cast(str, prompt_id),
            prompt_version=cast(str, prompt_version),
            variables=self._build_variables(inputs),
            model_alias=cast(str, model_alias),
            max_output_tokens=self._max_output_tokens,
            workflow_id=inputs.get("workflowId"),
            step_id=inputs.get("stepId"),
            agent_id=inputs.get("agentId"),
        )
        return {"content": result.response.content}

    @staticmethod
    def _build_variables(inputs: dict[str, Any]) -> dict[str, Any] | None:
        variables = dict(inputs.get("variables") or {})
        context = inputs.get("context")
        if isinstance(context, AssembledContext) and context.items:
            variables.setdefault("context", _flatten_context(context))
        return variables or None
