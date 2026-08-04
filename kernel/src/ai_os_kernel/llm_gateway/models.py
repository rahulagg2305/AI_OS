"""Minimal ``LLMRequest``/``LLMResponse`` contract shapes.

Field-for-field a deliberately reduced slice of the full Request/Response
Contract (docs/03_architecture/kernel/llm_gateway.md §4/§5) — the same
"trivial slice, not the whole document" pattern already used for
:mod:`ai_os_kernel.workflow_engine.agent`/:mod:`ai_os_kernel.workflow_engine.tool`.

**Included, from §4 (Request Contract), and why each survives the cut:**

- ``model_alias`` — REQUIRED, never a literal model id (ADR-0002: the
  platform is LLM-agnostic; this field is the entire mechanism that
  makes it so, not part of any subsystem this step defers).
- ``messages`` — the conversation itself; nothing is a request without it.
- ``system`` — reduced from the documented ``SystemBlock[]`` to a plain
  ``str | None``: §4 gives ``SystemBlock`` no further shape than its
  name, and the only reason a real implementation would need a *list*
  of blocks is per-block prompt-cache breakpoints (§8) — caching is out
  of scope this step. A single string is the honest remaining shape.
- ``max_output_tokens`` — every provider call needs a length bound;
  this is the request's own basic shape, not part of the deferred
  Budget Enforcer (which enforces a *workflow*/*experiment* cost
  ceiling, a different concern).
- ``metadata`` — **partially included**, as of the Policy & Budget
  Enforcer's per-workflow slice: reduced from the documented
  ``TraceContext`` (platform_sdk.md §4.1: ``trace_id; span_id;
  workflow_id?; step_id?; agent_id?; experiment_id?; run_id?`` —
  "Field names are normative") to three of its seven fields,
  ``workflow_id``/``step_id``/``experiment_id``, via the
  :class:`TraceContext` class below. ``experiment_id`` was added at
  ``P02-S07-M23-T02`` — the Response Cache's own ADR-0025 §3 hard rule
  ("unconditionally disabled for any run belonging to an experiment")
  has no way to hold without it; a real, structural gap found and
  resolved there, not part of this step's own original scope.
  ``trace_id``/``span_id`` (real values already exist via the
  OpenTelemetry span context ADR-0017 documents, but wiring that in is
  a distinct, later step — see :mod:`ai_os_kernel.llm_gateway.models`'s
  own note on :class:`TraceContext`) and ``agent_id``/``run_id`` (this
  step's own approved exclusions: no agent metadata, no run metadata)
  remain deliberately absent as fields — not present-but-``None``,
  because an always-``None`` field for a capability nothing populates
  would be exactly the "placeholder architecture" this step avoids.
  Whole-field ``metadata: TraceContext | None`` (not the documented
  contract's unconditionally-required ``TraceContext``) so every
  existing caller that never supplies it is completely unaffected.

**Excluded, each belonging to an explicitly deferred subsystem:**
``tools``/``tool_choice`` (tool-calling), ``response_format`` (structured
output), ``thinking``/``effort`` (capability-negotiated routing),
``stream`` (streaming), ``cache_hints`` (caching),
``budget``/``timeout_seconds`` (budgets), ``require_capabilities``
(capability negotiation and observability wiring beyond what this
minimal contract itself needs).

**Included, from §5 (Response Contract):**

- ``content`` — reduced from the documented ``ContentBlock[]``
  (``text | tool_call | thinking``) to a plain ``str``: only the
  ``text`` variant has meaning without tool-calling or thinking, both
  deferred; a one-variant discriminated union would be unnecessary
  structure for a single case.
- ``stop_reason`` — reduced from the documented five-value enum
  (``end_turn | max_tokens | tool_use | refusal | pause_turn``) to the
  two values a trivial, provider-free implementation can honestly
  produce: ``end_turn`` (normal completion) and ``max_tokens`` (hit its
  length bound). ``tool_use`` needs tool-calling, ``refusal`` needs a
  real model's judgment, ``pause_turn`` needs extended/agentic
  execution — none exist yet. ``stop_details`` (only ever accompanies
  ``refusal``) is dropped with it.
- ``usage`` — kept **complete** against §5's ``UsageRecord`` shape,
  including ``cache_read_tokens``/``cache_write_tokens`` (matching
  ``evaluation.llm_calls``' own already-built columns) and
  ``retries``/``fallback_used``: a trivial implementation can honestly
  report zero/false for all of them — a true statement ("no caching,
  retries, or fallback happened"), not an invented one.
- ``provider``/``model_id``/``model_version`` — a response claiming to
  be *from* something is core to what a response is, not part of the
  deferred Router (which decides *which* provider/model — a fixed,
  honestly-labelled sentinel here needs no routing to produce).

- ``served_from_cache`` — added at ``P02-S07-M23-T02``: the Response
  Cache's own real, disclosed reason for previously excluding this
  field ("caching... out of scope this step") no longer applies.
  Defaults ``False`` — every existing caller not going through the
  cache is completely unaffected; :class:`~ai_os_kernel.caching.
  response_cache.ResponseCache` is the one place that ever sets it
  ``True``, on a genuine cache hit.

**Excluded from the response:** ``degradations`` (capability
negotiation), ``raw`` (a debug passthrough for a real provider payload
that does not exist here).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageRole(StrEnum):
    """A message's speaker. ``system`` is deliberately not a role here —
    §4 keeps the system prompt a separate top-level field, not part of
    the ``messages`` list."""

    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """One turn in the conversation."""

    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str


class TraceContext(BaseModel):
    """A deliberately minimal slice of platform_sdk.md §4.1's canonical
    ``TraceContext`` (``trace_id; span_id; workflow_id?; step_id?;
    agent_id?; experiment_id?; run_id?`` — "Field names are normative").

    Carries ``workflow_id``/``step_id`` (the LLM Gateway's Policy &
    Budget Enforcer's own per-workflow cost ceiling, llm_gateway.md §9:
    "Workflow cost ceiling | BudgetExceededError") and, as of
    ``P02-S07-M23-T02``, ``experiment_id`` — the Response Cache's own
    ADR-0025 §3 hard rule ("unconditionally disabled for any run
    belonging to an experiment") needs a real field to check; there was
    none. The other four documented fields are still not present here
    at all, by deliberate choice, not oversight:

    - ``trace_id``/``span_id`` (distributed-trace correlation) already
      have real values available today — ADR-0017/observability.md
      document them as propagated via the OpenTelemetry span context
      that this Kernel's own tracing instrumentation already creates
      (``ai_os_kernel.observability.tracing``) — but *reading* that
      context and threading it through here is a distinct, later step
      (Observability integration, not Policy & Budget), so it is left
      out entirely rather than added as a field nothing populates.
    - ``agent_id``/``run_id`` are this step's own approved exclusions
      ("no agent metadata, no run metadata").

    Both these exclusions and the "not yet wired" ``trace_id``/
    ``span_id`` are absent as *fields*, not present as always-``None``
    ones — an always-``None`` field for a capability nothing populates
    would be exactly the "placeholder architecture" this step is
    required to avoid. Adding any of the remaining four once a real
    source exists is a strictly additive, non-breaking change to this
    class, the identical shape ``experiment_id`` itself was just added
    by.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: str | None = None
    step_id: str | None = None
    experiment_id: str | None = None
    """``None`` means "not part of an experiment" — the Response Cache
    (:class:`~ai_os_kernel.caching.response_cache.ResponseCache`)
    treats any non-``None`` value as an unconditional cache bypass,
    per ADR-0025 §3."""


class LLMRequest(BaseModel):
    """A request to complete a conversation — see this module's
    docstring for exactly which fields of the full §4 contract this
    covers, and why."""

    model_config = ConfigDict(frozen=True)

    model_alias: str
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
    """Reduced from §5's five-value enum to the two this step's trivial
    implementation can honestly produce — see this module's docstring."""

    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"


class UsageRecord(BaseModel):
    """Kept complete against §5's documented shape — see this module's
    docstring for why every field is included even though several are
    always zero/false at this step."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    latency_ms: int
    provider: str
    model_id: str
    retries: int
    fallback_used: bool


class LLMResponse(BaseModel):
    """A completed request's result — see this module's docstring for
    exactly which fields of the full §5 contract this covers, and why."""

    model_config = ConfigDict(frozen=True)

    content: str
    stop_reason: StopReason
    usage: UsageRecord
    provider: str
    model_id: str
    model_version: str
    served_from_cache: bool = False
    """``True`` only when :class:`~ai_os_kernel.caching.response_cache.
    ResponseCache` returned this response from a real cache hit — every
    other caller's response is a genuine model output. ADR-0025 §3:
    the Evaluation Engine excludes ``served_from_cache=true`` runs from
    comparison results."""


class EmbeddingRequest(BaseModel):
    """A request for real embedding vectors (§11), added at
    ``P02-S02-M06-T09``. Field-for-field §11's own documented shape
    (``model_alias; inputs: str[]; metadata: TraceContext``) — ``inputs``
    is a real batch, not one text at a time, matching every real
    embeddings endpoint's own batch-native wire shape."""

    model_config = ConfigDict(frozen=True)

    model_alias: str
    inputs: list[str]
    metadata: TraceContext | None = None

    @field_validator("model_alias")
    @classmethod
    def _model_alias_is_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("model_alias must not be blank — never a literal model id (ADR-0002)")
        return value

    @field_validator("inputs")
    @classmethod
    def _at_least_one_input(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("inputs must contain at least one text")
        return value


class EmbeddingResponse(BaseModel):
    """§11's own documented response shape (``vectors: float[][];
    model_id; model_version; dimensions; usage: UsageRecord``) —
    ``usage`` is the same shape :class:`LLMResponse` already uses
    (``retries``/``fallback_used`` are honestly ``0``/``False``: real
    embedding calls never retry or fall back — see
    :meth:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway.embed`'s
    own docstring for why)."""

    model_config = ConfigDict(frozen=True)

    vectors: list[list[float]]
    model_id: str
    model_version: str
    dimensions: int
    usage: UsageRecord


class StreamEventType(StrEnum):
    """§4.3's own documented six-value event set, minus ``error`` —
    added at ``P02-S02-M06-T08``. A real provider streaming failure
    surfaces as :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`
    raised out of the generator, the identical channel every other
    real failure in this Gateway already uses, rather than a second,
    parallel in-band error-delivery event type."""

    MESSAGE_START = "message_start"
    CONTENT_START = "content_start"
    CONTENT_DELTA = "content_delta"
    CONTENT_STOP = "content_stop"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_STOP = "message_stop"


class LLMStreamEvent(BaseModel):
    """§4.3's own documented shape (``type; index; delta; content_block?;
    usage?``), reduced the identical way :class:`LLMResponse.content`
    already is: ``content_block`` is dropped entirely rather than kept
    as an always-``None`` field, since this reduced contract never
    declares tools/thinking and therefore only ever emits real ``text``
    content blocks — a caller already knows the one real shape a
    content block can have without this field naming it. ``delta`` is
    reduced from a typed delta object to the real, incremental text
    string itself, the identical "only the ``text`` variant has
    meaning without tool-calling or thinking" reasoning
    :class:`LLMResponse.content` already documents.

    ``usage`` is genuinely ``None`` except on ``message_delta`` — §4.3
    says "usage totals arrive on ``message_delta``/``message_stop``",
    and that is honestly what happens for the one real provider this
    reduced contract streams from: Anthropic's own real
    ``message_stop`` event carries no usage field of its own at all: a
    real absence, not a value this adapter withholds.
    """

    model_config = ConfigDict(frozen=True)

    type: StreamEventType
    index: int | None = None
    delta: str | None = None
    usage: UsageRecord | None = None
