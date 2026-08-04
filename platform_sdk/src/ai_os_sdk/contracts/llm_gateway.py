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

``stream()``, ``embed()``, and ``count_tokens()`` are **not defined on
this Protocol in v1.0.0** — declaring one here would ship a method
every implementation must satisfy, and not every real
``LLMGateway``/adapter can honestly do so.

**Updated 2026-08-04 (Kernel-side, `P02-S02-M06-T10`):**
``AnthropicAdapter`` now genuinely implements token counting against
Anthropic's own real ``/v1/messages/count_tokens`` endpoint
(``kernel/src/ai_os_kernel/llm_gateway/adapters/anthropic_adapter.py``),
and ``DispatchingLLMGateway.count_tokens()`` dispatches to it via a
Kernel-local ``TokenCounter`` Protocol — but this SDK-level
``LLMGateway`` Protocol is intentionally unchanged: adding
``count_tokens()`` here, per §8, is still its own, separate **minor**
SDK version bump, not implied by a Kernel-side capability existing.
``stream()``/``embed()`` remain unbacked by any real adapter.
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
