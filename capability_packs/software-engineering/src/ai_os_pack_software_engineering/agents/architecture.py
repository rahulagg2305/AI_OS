"""The Architecture Agent — agent_architecture.md's "Agent Categories
(Initial Target)" #2, this pack's first real increment. Given a
software requirement, proposes a concrete technical design. No code
generation, no Build/Test/Documentation Agents, no approval gating —
output capture only, exactly this step's own approved scope.

**Reuses ``PromptedAgent`` unchanged — does not reinvent agent
invocation logic.** :class:`ArchitectureAgentEntrypoint` is a thin
wrapper whose ``execute()`` delegates entirely to a real, internally
constructed :class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`.
Its own ``output_schema`` is a literal copy of
:attr:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent.output_schema`
(``{"content": <string>}``) — kept manually in sync the same way
:class:`~ai_os_kernel.workflow_engine.tool.EchoTool`'s own schema is
independent of any shared source, since this wrapper's ``execute()``
output *is* whatever ``PromptedAgent.execute()`` returns, unmodified.

**Why this class exists at all, instead of registering a
``PromptedAgent`` directly — the documented, reasoned resolution to
this step's own named tension.** :class:`~ai_os_kernel.workflow_engine.
entrypoint_loader.EntrypointLoader` always constructs an entrypoint
with zero arguments (``cls()``) — its own docstring states why:
"Passing manifest-declared configuration into an entrypoint's
constructor is real Capability Manager design work, not attempted
here." ``PromptedAgent`` itself cannot be that zero-arg entrypoint: it
needs a real, already-constructed ``PromptedCompletionService``
(database engine, resolved secret, model/pricing configuration) —
:mod:`ai_os_kernel.workflow_engine.prompted_agent`'s own docstring
already documents this exact incompatibility and its previously-
established resolution: "used through ``InMemoryAgentRegistry`` ...
Making a dependency-carrying agent loadable via ``SqlAgentRegistry``'s
real entrypoint mechanism would require passing it real configuration
at construction time." This step's own approved framing asks for
exactly that resolution, decided and recorded rather than silently
worked around: **``ArchitectureAgentEntrypoint`` is genuinely
zero-argument-constructible (satisfying ``EntrypointLoader`` and
therefore ``SqlAgentRegistry``), and lazily builds its own real
``PromptedAgent`` on first ``execute()`` call** — not in ``__init__``,
because building a real ``PromptedCompletionService`` needs ``await``
(:func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`
is async), and ``__init__`` cannot be. This changes nothing about
``EntrypointLoader`` itself (it remains zero-arg-only, unmodified) —
the boundary is respected, not silently broken; construction merely
defers real work to the first genuinely async call this Protocol
already has (``execute``), guarded by a lock so concurrent first calls
build exactly one shared instance.

**A known, documented, temporary architectural compromise: this pack
imports Kernel internals directly.** capability_pack_contract.md's own
"Platform Interaction Rules" name the Platform SDK as a pack's only
sanctioned interaction surface ("Direct Kernel access is prohibited"),
but no ``ai-os-sdk`` package exists yet (kernel's own ``pyproject.toml``
lists it under "Planned, not yet scaffolded") — there is nothing else
honest for this agent to depend on for a real LLM Gateway/Prompt
Engine/database connection. This module therefore reuses
:func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`
directly, the identical real composition ``kernel/bootstrap.py`` itself
already uses for its own demo ``PromptedAgent`` — reuse, not a second,
divergent way to assemble the same real pieces. Replacing this with a
Platform SDK ``PackContext``-supplied service is that future SDK's own
migration to make; this pack's own ``pyproject.toml`` records the same
compromise from the dependency-declaration side.

**No resilience features configured** (no circuit breaker, backoff
policy, or budget enforcer) — the identical, simplest valid call shape
``tests/integration/workflow_engine/test_prompted_agent_live.py``
already establishes for a first real Agent-to-provider proof; adding
them is a distinct, later concern once this pack has more than one
agent to share a policy across.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import PROVIDER_NAME
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.prompted_completion import (
    PromptedCompletionService,
    build_anthropic_prompted_completion_service,
)
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent

# Mirrors bootstrap.py's own identical constant — the one documented
# local-dev secret reference for a real Anthropic API key (ADR-0024).
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

# A named, documented first-cut value, not yet tuned against real
# architecture-proposal output lengths — the same "placeholder safety
# limit" carve-out kernel/bootstrap.py's own policy constants already
# use, not a magic number.
_MAX_OUTPUT_TOKENS = 2048

# Mirrors PromptedAgent.output_schema exactly — see this module's own
# docstring for why this is a literal copy, not a derived reference.
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
    "additionalProperties": False,
}

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"


class ArchitectureProposalInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md) — the manifest's own required
    ``inputSchema`` field names this model. **Not yet validated at
    runtime**: no per-step input-mapping mechanism exists in this
    codebase to check any agent's inputs against a declared schema
    (:mod:`ai_os_kernel.workflow_engine.agent`'s own long-established,
    unchanged scope). Today, ``requirement`` reaches this agent only via
    the Context Manager's own assembled ``context`` prompt variable
    (a workflow's own declared ``inputs``, flattened) — the one real
    channel ``AgentStepExecutor``/``PromptedAgent`` already establish;
    this field records the documented contract, not a second, real
    input path.
    """

    requirement: str = Field(
        ..., description="The software requirement or specification to design for."
    )


class ArchitectureProposalOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    :attr:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent.output_schema`
    exactly: free-text content (a design proposal, per this agent's
    prompt), not a structured object — this agent reuses ``PromptedAgent``
    unchanged, so its real output shape is whatever that class returns.
    """

    content: str = Field(..., description="The proposed architecture and design, as free text.")


async def _build_real_service() -> PromptedCompletionService:
    """The real, production composition — reuses
    :func:`~ai_os_kernel.prompted_completion.build_anthropic_prompted_completion_service`,
    the identical function ``kernel/bootstrap.py`` itself already calls
    for its own demo agent. See this module's own docstring for why a
    pack needs to call this Kernel-internal function directly today."""
    provider_config = load_provider_config(_CONFIG_PATH)
    router = StaticRouter(
        routes={
            alias: RoutingDecision(
                provider=provider_config.providers.get(alias, PROVIDER_NAME), model_id=model_id
            )
            for alias, model_id in provider_config.model_ids.items()
        }
    )
    engine = build_engine(DatabaseSettings().database_url)
    return await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=router,
        pricing=provider_config.pricing,
    )


class ArchitectureAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Architecture
    Agent — zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`),
    lazily delegating to a real, internally-built
    :class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`
    on first :meth:`execute` call. See this module's own docstring for
    the full reasoning.

    ``service_factory`` is an optional constructor override — always
    ``None`` in production (``EntrypointLoader`` only ever calls
    ``cls()``), and how a test substitutes a deterministic
    ``PromptedCompletionService`` (an ``EchoLLMGateway``-backed one, for
    example) without touching the real composition at all. This does
    not weaken the zero-arg boundary: the parameter is optional and
    defaulted, so ``cls()`` still succeeds in production exactly as
    ``EntrypointLoader`` requires.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        service_factory: Callable[[], Awaitable[PromptedCompletionService]] | None = None,
    ) -> None:
        self._service_factory = service_factory or _build_real_service
        self._agent: PromptedAgent | None = None
        self._build_lock = asyncio.Lock()

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        agent = await self._ensure_agent()
        return await agent.execute(inputs)

    async def _ensure_agent(self) -> PromptedAgent:
        async with self._build_lock:
            if self._agent is None:
                service = await self._service_factory()
                self._agent = PromptedAgent(service=service, max_output_tokens=_MAX_OUTPUT_TOKENS)
        return self._agent
