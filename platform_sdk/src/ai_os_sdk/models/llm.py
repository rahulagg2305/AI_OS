"""The ``LLMGateway`` boundary models (``platform_sdk.md`` §5.1).

**These are the narrowed v1.0.0 shapes**, per §5.1's dated
*v1.0.0 Reconciliation Decision* block (``platform_sdk_v1_scope.md``
step 2a) and its step-4 addendum. §5.1's prose documents a considerably
richer contract — ``tools``/``tool_choice`` (tool-calling),
``response_format`` (structured output), ``thinking``/``effort``
(capability-negotiated routing), ``cache_hints`` (prompt caching),
``budget`` (per-request budget), and a five-value ``stop_reason``
(``end_turn|max_tokens|tool_use|refusal|pause_turn``). None of that has
a real caller: the working ``DispatchingLLMGateway`` and its one real
provider adapter implement none of tool-calling, structured output,
thinking, caching, or streaming today (``llm_gateway/gateway.py``'s own
docstring lists these as explicitly out of scope). Building the richer
shape now would mean validating requests against capabilities nothing
can honour.

``LLMRequest``, ``Message``, ``MessageRole``, ``StopReason``,
``UsageRecord``, and ``LLMResponse`` below are therefore **field-for-field
mirrors of the real, working**
``ai_os_kernel.llm_gateway.models`` **shapes** — narrowed exactly as far
as the Kernel's own models are narrowed, no further and no less. Only
``ProviderCapabilities`` differs from that mirror: it is **extended**
past both the original §5.1 prose (10 fields) and matches the real,
already-13-field Kernel shape, because the real
``StaticCapabilityNegotiator`` genuinely implements all 13 and its own
docstring names §5.1 as "the discrepancy it implements past."

Widening any of these mirrored models toward the full §5.1 shape is a
future, deliberate step — scheduled together with whichever Gateway
capability (tool-calling, structured output, caching, streaming) the
new field would actually serve, not added speculatively ahead of it.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_os_sdk.models.common import TraceContext


class MessageRole(StrEnum):
    """A message's speaker. ``system`` is deliberately not a role here —
    the system prompt is a separate top-level field (:attr:`LLMRequest.
    system`), not part of the conversation list, mirroring the real
    Kernel's identical exclusion."""

    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """One turn in the conversation."""

    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str


class LLMRequest(BaseModel):
    """A request to complete a conversation — the narrowed shape; see
    this module's docstring for exactly which fields of the full §5.1
    contract this covers, and why."""

    model_config = ConfigDict(frozen=True)

    model_alias: str
    """Never a literal model id (ADR-0002) — this field is the entire
    mechanism that keeps the platform LLM-agnostic."""

    messages: list[Message]
    system: str | None = None
    max_output_tokens: int = Field(gt=0)
    metadata: TraceContext | None = None

    @field_validator("model_alias")
    @classmethod
    def _model_alias_is_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("model_alias must not be blank — never a literal model id (ADR-0002)")
        return value

    @field_validator("messages")
    @classmethod
    def _at_least_one_message(cls, value: list[Message]) -> list[Message]:
        if not value:
            raise ValueError("messages must contain at least one message")
        return value


class StopReason(StrEnum):
    """Narrowed from §5.1's documented five-value enum
    (``end_turn | max_tokens | tool_use | refusal | pause_turn``) to the
    two values a tool-free, structured-output-free, non-streaming
    completion can honestly produce — mirroring the real Kernel's
    identical reduction. ``tool_use``/``refusal``/``pause_turn`` arrive
    together with tool-calling, model-refusal handling, and streaming
    respectively; adding one without its capability would be a stop
    reason nothing can ever actually return.
    """

    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"


class UsageRecord(BaseModel):
    """Token, cost, and retry accounting for one completion. Kept
    complete against §5.1's documented shape — every field is
    meaningful even where a trivial provider always reports zero/false
    for some of them.

    Non-negativity is an SDK-added invariant, not present as a field
    constraint on the Kernel's own model: a negative token count, cost,
    latency, or retry count is never a real value, only a bug, and
    validating it here catches that at the boundary rather than letting
    it propagate into `evaluation.llm_calls`.
    """

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)
    """Never a float (``data_model.md`` §2: "Never floating point")."""
    latency_ms: int = Field(ge=0)
    provider: str
    model_id: str
    retries: int = Field(ge=0)
    fallback_used: bool


class LLMResponse(BaseModel):
    """A completed request's result — the narrowed shape; see this
    module's docstring for exactly which fields of the full §5.1
    contract this covers, and why.

    ``content`` is narrowed from the documented ``ContentBlock[]``
    (``text | tool_call | thinking``) to a plain ``str``: only the
    ``text`` variant has meaning without tool-calling or thinking, both
    unimplemented, so a one-variant discriminated union would be
    structure with nothing to discriminate.
    """

    model_config = ConfigDict(frozen=True)

    content: str
    stop_reason: StopReason
    usage: UsageRecord
    provider: str
    model_id: str
    model_version: str


class ProviderCapabilities(BaseModel):
    """One model's capability matrix (``platform_sdk.md`` §5.1).

    **Extended past the original §5.1 prose (10 fields) to the real,
    working 13-field shape** — the reverse direction from every other
    model in this module. The real ``StaticCapabilityNegotiator``
    already implements all 13, and that class's own docstring names
    §5.1 as "the platform_sdk.md discrepancy this implements past." The
    three fields the original prose omitted: ``supports_strict_tools``,
    ``prompt_cache_min_tokens``, ``accepts_sampling_params``.

    ``max_input_tokens``/``max_output_tokens`` here are the *provider's*
    own ceilings — a fact about the model, unrelated to
    :attr:`LLMRequest.max_output_tokens`, which is a caller's own
    per-request choice. Nothing validates one against the other; that
    is capability-dependent request validation, which has no caller
    until tool-calling or structured output exist.
    """

    model_config = ConfigDict(frozen=True)

    supports_tools: bool
    supports_parallel_tool_calls: bool
    supports_strict_tools: bool
    supports_structured_output: bool
    supports_streaming: bool
    supports_thinking: bool
    supports_effort: bool
    supports_prompt_caching: bool
    prompt_cache_min_tokens: int | None
    supports_vision: bool
    max_input_tokens: int
    max_output_tokens: int
    accepts_sampling_params: bool

    @model_validator(mode="after")
    def _prompt_cache_min_tokens_matches_support(self) -> ProviderCapabilities:
        if self.supports_prompt_caching and self.prompt_cache_min_tokens is None:
            raise ValueError(
                "prompt_cache_min_tokens must be set when supports_prompt_caching is true"
            )
        if not self.supports_prompt_caching and self.prompt_cache_min_tokens is not None:
            raise ValueError(
                "prompt_cache_min_tokens must be omitted when supports_prompt_caching is false "
                "— a minimum for a capability this model does not have would be meaningless"
            )
        return self

    @model_validator(mode="after")
    def _token_ceilings_are_positive(self) -> ProviderCapabilities:
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0:
            raise ValueError("max_input_tokens and max_output_tokens must both be positive")
        return self
