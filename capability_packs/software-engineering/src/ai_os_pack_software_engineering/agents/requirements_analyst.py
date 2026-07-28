"""The Requirements Analyst Agent — agents.md's own Agent Catalog #1
(`software-engineering/requirements-analyst`), the natural upstream
predecessor to the Architecture Agent this pack already has: given a
raw software requirement or ask, produce a structured, refined
requirements analysis an Architecture Agent (or a human) can design
against. No code generation, no architecture design, no validation
against acceptance criteria beyond what the model itself states —
output capture only, the identical scope reduction every agent in this
pack has used for its own first real slice.

**Reuses `PromptedAgent` unchanged, via the identical zero-arg/lazy-build
pattern `ArchitectureAgentEntrypoint` already established — invents no
new mechanism.** This agent needs no sandbox at all (it produces text,
not a file) and no completion-text parsing (its whole output *is* the
model's own completion, verbatim) — the simplest possible shape this
pack's own four prior agents have already proven, structurally
identical to `ArchitectureAgentEntrypoint` in every respect but its own
prompt/input field name (`requirement` here too, matching the same
free-text convention) and output field name (`analysis` in place of
`content`, since this agent's own output is a structured requirements
analysis, not a design proposal — the two are conceptually distinct
Agent Contract "Produced Outputs," so given their own names rather than
reusing Architecture's `content` field name by accident of having an
identical shape).

**Composes the identical real production service every other
`PromptedAgent`-backed agent in this pack already does — not a second,
divergent way to assemble the same pieces.** See
:mod:`ai_os_pack_software_engineering.agents.architecture`'s own
docstring for the full reasoning behind
`build_anthropic_prompted_completion_service()` reuse, the
zero-argument/lazy-build resolution to the `EntrypointLoader`
incompatibility, and the "this pack imports Kernel internals directly"
documented, temporary compromise — all identical here, not repeated in
full.
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

# Mirrors architecture.py's own identical constant exactly.
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

# Named, documented first-cut value, not yet tuned against real
# requirements-analysis output lengths — the same "placeholder safety
# limit" carve-out every agent in this pack already uses.
_MAX_OUTPUT_TOKENS = 2048

# This agent's own output field is `analysis`, not `PromptedAgent`'s own
# `content` — see this module's own docstring for why. Mapping one onto
# the other happens in `execute()` below, not by reusing `PromptedAgent`
# .output_schema literally, unlike `ArchitectureAgentEntrypoint`.
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"analysis": {"type": "string"}},
    "required": ["analysis"],
    "additionalProperties": False,
}

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"


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


class RequirementsAnalysisOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs" — free
    text (a structured requirements analysis, per this agent's own
    prompt), not a further-structured object. Named ``analysis``, not
    ``content``, per this module's own docstring."""

    analysis: str = Field(
        ..., description="The refined, structured requirements analysis, as free text."
    )


async def _build_real_service() -> PromptedCompletionService:
    """The real, production composition — identical to
    :func:`ai_os_pack_software_engineering.agents.architecture._build_real_service`.
    Not shared as a common helper — see that module's own docstring for
    the ADR-0004 reasoning every agent module in this pack already
    applies to its own copy of this same, already-minimal composition.
    """
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


class RequirementsAnalystAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Requirements
    Analyst Agent — zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`),
    lazily delegating to a real, internally-built
    :class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent`
    on first :meth:`execute` call — the identical pattern
    :class:`~ai_os_pack_software_engineering.agents.architecture.
    ArchitectureAgentEntrypoint` already establishes, reused, not
    reinvented.

    ``service_factory`` is an optional constructor override — always
    ``None`` in production (``EntrypointLoader`` only ever calls
    ``cls()``), and how a test substitutes a deterministic
    ``PromptedCompletionService`` without touching the real composition.
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
        completion_outputs = await agent.execute(inputs)
        return {"analysis": completion_outputs["content"]}

    async def _ensure_agent(self) -> PromptedAgent:
        async with self._build_lock:
            if self._agent is None:
                service = await self._service_factory()
                self._agent = PromptedAgent(service=service, max_output_tokens=_MAX_OUTPUT_TOKENS)
        return self._agent
