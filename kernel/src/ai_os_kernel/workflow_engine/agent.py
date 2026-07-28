"""The minimal Agent contract the Workflow Engine needs to invoke an
Agent-type step.

This is a deliberately reduced slice of the full Agent Contract in
docs/03_architecture/agents/agent_architecture.md. That document's
invocation lifecycle is: assemble context via the Context Manager,
build an ``AgentRequest`` (context, security context, budget,
deadline), validate against ``input_model``, execute — requesting
prompts, calling the LLM Gateway, invoking Tools — validate against
``output_model``, and return an ``AgentResult``. The Prompt Registry,
the LLM Gateway's own request contract, and the Tool Invoker remain out
of scope here. What remains, and what this module implements, is
exactly what the approved step asked for: ``agent.execute(inputs) ->
outputs``, with the declared ``output_schema`` — the Agent Contract's
required ``outputs`` field — enforced by the caller
(:mod:`ai_os_kernel.workflow_engine.step_executor`).

**Context assembly is no longer out of scope, but the ``Agent``
Protocol's own shape did not need to change for that to be true.** The
Context Manager's first real slice (:mod:`ai_os_kernel.context_manager`)
is now optionally wired into
:class:`~ai_os_kernel.workflow_engine.step_executor.AgentStepExecutor`,
which adds its result to ``inputs`` under a ``"context"`` key when
configured — a real :class:`~ai_os_kernel.context_manager.models.
AssembledContext`, consumed so far only by
:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`
(agent_architecture.md's "Context Consumer" role). This ``Agent``
Protocol's ``execute(inputs: dict) -> dict`` shape absorbs it without
change, exactly the same way it already absorbs
``promptId``/``promptVersion``/``modelAlias`` below —
:class:`EchoAgent` still ignores whatever key `inputs` carries, context
included.

Input validation against a declared ``input_schema`` is still not
included: no general per-step input-mapping mechanism exists (context
assembly is a distinct, additive concern — *what* the Context Manager
supplies, not per-step schema-declared inputs, which remain
undeclared). What does exist is narrower —
:class:`~ai_os_kernel.workflow_engine.step_executor.AgentStepExecutor`
forwards a step's own declared ``promptId``/``promptVersion``/
``modelAlias`` (workflow_architecture.md's Step Contract) into
``inputs`` unmodified, since those three fields are the only ones the
Step Contract documents for an agent step and agent_architecture.md is
explicit the Workflow Engine "passes them through without acting on
them itself." A step declaring none of them, with no Context Manager
configured, still executes with an empty ``inputs`` dict, exactly as
every agent invocation did before — :class:`EchoAgent` below still
ignores whatever it receives either way. Adding an unused
``input_schema`` now would still be a half-finished field, not a
contract.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """One trivial, in-process unit of work. No LLM Gateway access, no
    tool access, no context — those seams belong to later steps.

    ``@runtime_checkable`` so
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry` can
    ``isinstance``-check a dynamically loaded entrypoint before handing
    it back — a structural presence check only (does it have
    ``output_schema``/``execute``), not a signature or type check, but
    enough to turn "an entrypoint resolved to something unrelated" into
    a clear error instead of a confusing failure the first time
    something calls ``.execute()``.
    """

    output_schema: dict[str, Any]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]: ...


class EchoAgent:
    """The one trivial in-process agent implementation for this step.

    Does no real work and never will need to — it exists to prove the
    invocation path (call, validate, return) works end to end.
    """

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"status": {"const": "ok"}},
        "required": ["status"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}
