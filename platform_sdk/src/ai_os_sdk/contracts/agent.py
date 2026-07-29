"""The ``Agent`` Protocol a Capability Pack implements
(``platform_sdk.md`` §4.2).

**This is the narrowed v1.0.0 shape**, per that section's dated
*v1.0.0 Reconciliation Decision* block (recorded 2026-07-29,
``platform_sdk_v1_scope.md`` step 2a) — not §4.2's prose shape, which
remains the approved long-term target. The prose specifies
``execute(request: AgentRequest) -> AgentResult`` with ``agent_id``/
``version``/``input_model``/``output_model``; this Protocol is
deliberately the dict-based shape five real, proven agents already
satisfy, so that migrating them onto this SDK (steps 9–13) requires no
change to the Workflow Engine's calling convention.

``AgentRequest``/``AgentResult`` are therefore **not defined anywhere in
v1.0.0** — they have no consumer under this shape. Introducing them is a
future **major** SDK change (§8), scheduled together with the Workflow
Engine change it requires.

**What this Protocol deliberately does not carry.** ``SecurityContext``,
``StepBudget``, and ``TraceContext`` are not named fields here; they
reach an agent as entries in the ``inputs`` mapping. That is not a new
compromise introduced by this SDK — the Workflow Engine already passes a
real ``AssembledContext`` object under an ``inputs`` key today, so
``inputs`` has always been a ``dict[str, Any]`` carrying rich objects
rather than a flat string map. See §4.2's decision block for the full
cost record.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """One unit of agent work owned by a Capability Pack.

    Agents are **stateless between invocations** (``platform_sdk.md``
    §4.2); any state that must survive belongs in Workflow State. An
    agent never calls another agent — coordination is the Workflow
    Engine's alone (ADR-0005, "agents never communicate directly").

    ``@runtime_checkable`` so a loader can reject an entrypoint that
    resolved to something structurally unrelated before anything calls
    it. **Be precise about what that check proves:** a
    ``runtime_checkable`` Protocol's ``isinstance`` verifies *member
    presence only* — never signatures, never annotations. An object with
    an ``output_schema`` attribute and an ``execute`` attribute passes,
    whatever their shapes. It converts "this entrypoint is not remotely
    an agent" into a clear error; it does not certify the contract.
    """

    output_schema: dict[str, Any]
    """JSON Schema the agent's returned mapping is validated against by
    its caller. A declared schema is what makes an agent's output a
    contract rather than a convention."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Perform this agent's work and return its structured output.

        ``inputs`` carries whatever the invoking step supplied. Values
        may be rich objects, not only strings — see this module's own
        docstring.
        """
        ...
