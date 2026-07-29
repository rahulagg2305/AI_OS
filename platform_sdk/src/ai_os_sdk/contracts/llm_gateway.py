"""The ``LLMGateway`` Protocol — the sole route to any model
(``platform_sdk.md`` §5.1, ADR-0002, "LLM Gateway single entry point").

**This is the narrowed v1.0.0 shape**, per §5.1's dated
*v1.0.0 Reconciliation Decision* block (recorded 2026-07-29,
``platform_sdk_v1_scope.md`` step 2a) — not §5.1's prose, which
documents five methods (``complete``/``stream``/``embed``/
``count_tokens``/``capabilities``) and remains the approved long-term
target. The real, working ``DispatchingLLMGateway`` implements exactly
two of them; this Protocol is exactly that shape, so the real class
satisfies it without modification.

``stream()``, ``embed()``, and ``count_tokens()`` are **not defined
anywhere in v1.0.0** — no provider adapter implements streaming,
embeddings, or token counting, so declaring them would ship methods
every real adapter must raise from. Adding one later, once a real
adapter backs it, is a **minor** SDK version bump (§8): additive for
every existing caller.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_os_sdk.models.llm import LLMRequest, LLMResponse, ProviderCapabilities


@runtime_checkable
class LLMGateway(Protocol):
    """The sole seam through which anything in AI_OS may request a
    model completion. No provider SDK, no literal model id, and no
    direct HTTP call to a provider endpoint may appear in pack code
    (``platform_sdk.md`` §10) — a pack reaches a model only through an
    object satisfying this Protocol.

    ``@runtime_checkable`` for the same reason, and with the same
    limitation, as :class:`~ai_os_sdk.contracts.agent.Agent`: the
    ``isinstance`` check proves member presence only, never signatures.
    """

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete one conversation.

        Routing, retry, fallback, circuit-breaking, and budget
        enforcement all happen behind this call — a caller never
        chooses a provider or a concrete model id, only a
        ``model_alias``.
        """
        ...

    def capabilities(self, model_alias: str) -> ProviderCapabilities:
        """The capability matrix for whichever model ``model_alias``
        currently resolves to.

        Synchronous and side-effect-free — a fact lookup, unlike
        :meth:`complete`. A caller must never see a model id: the
        parameter is the alias, and resolution to a real model happens
        behind this call, exactly as it does for :meth:`complete`.
        """
        ...
