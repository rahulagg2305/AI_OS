"""LLM Gateway — the only component permitted to call a model provider.

See docs/03_architecture/kernel/llm_gateway.md, ADR-0002.

Implemented so far (Stage B, minimal first slice):

- :class:`LLMGateway` — the ``Protocol`` seam, with a single
  ``complete(request) -> response`` method.
- :class:`LLMRequest`/:class:`LLMResponse` (and their supporting types
  :class:`Message`/:class:`MessageRole`/:class:`StopReason`/
  :class:`UsageRecord`) — a deliberately reduced slice of the full
  Request/Response Contract (§4/§5). See
  :mod:`ai_os_kernel.llm_gateway.models` for exactly which fields of the
  documented contract are included and which are deferred, and why.
- :class:`EchoLLMGateway` — the one trivial in-process implementation,
  mirroring :class:`ai_os_kernel.workflow_engine.agent.EchoAgent`/
  :class:`ai_os_kernel.workflow_engine.tool.EchoTool`. No provider SDK,
  no adapter, no routing, no budgets, no capability negotiation, no
  caching, no streaming, no retries — see
  :mod:`ai_os_kernel.llm_gateway.gateway` for what it does instead and
  why that is enough to prove the contract end to end.
- :class:`LLMCallRecorder`/:class:`SqlLLMCallRecorder` — the minimal
  write path for ``evaluation.llm_calls`` (§13's Observability
  subsystem, reduced to exactly one write). Composed explicitly by a
  caller after :meth:`LLMGateway.complete` returns — see
  :mod:`ai_os_kernel.llm_gateway.call_recorder` for why this is not a
  ``LLMGateway``-conforming decorator, and for the ``agent_id``/
  ``prompt_id``/``prompt_version`` "optional on the call path, but the
  schema requires all three together" handling.
- :class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.
  AnthropicAdapter` — the first real, provider-backed ``LLMGateway``
  implementation, calling Anthropic via ``anthropic.AsyncAnthropic``
  (the only module permitted to import that SDK — see
  :mod:`ai_os_kernel.llm_gateway.adapters`). Resolves ``model_alias`` to
  a real model id and per-model pricing through
  :func:`~ai_os_kernel.llm_gateway.adapters.model_config.load_provider_config`
  (a flat, configuration-driven mapping — not the Router), and its own
  API key through :class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`
  via :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`.
  :class:`EchoLLMGateway` remains the deterministic, no-network
  implementation for tests and local development — this adapter does
  not replace it.

Not yet implemented: the Router's alias *chains*/fallback/provider
health/experiment pinning, the Policy & Budget Enforcer, capability
negotiation, prompt caching, streaming, and rate limiting (§3's
remaining internal subsystems — the SDK's own default retry behaviour
is the only retry present, and it is the SDK's, not this Gateway's).
Prompt Engine and Context Manager integration beyond this minimal
contract is also out of scope — nothing here assembles context or
renders a prompt, and nothing calls the Gateway from a real agent or
workflow step yet.
"""

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    AnthropicAdapter,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import (
    LLMProviderConfig,
    ModelPricing,
    load_provider_config,
)
from ai_os_kernel.llm_gateway.call_recorder import LLMCallRecorder, SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.errors import (
    LLMCallRecordingError,
    LLMProviderError,
    LLMRefusalError,
)
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway, LLMGateway
from ai_os_kernel.llm_gateway.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    StopReason,
    UsageRecord,
)

__all__ = [
    "AnthropicAdapter",
    "EchoLLMGateway",
    "LLMCallRecorder",
    "LLMCallRecordingError",
    "LLMGateway",
    "LLMProviderConfig",
    "LLMProviderError",
    "LLMRefusalError",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "MessageRole",
    "ModelPricing",
    "SqlLLMCallRecorder",
    "StopReason",
    "UsageRecord",
    "build_anthropic_adapter",
    "load_provider_config",
]
