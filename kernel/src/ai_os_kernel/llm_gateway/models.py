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
  "Field names are normative") to exactly two of its seven fields,
  ``workflow_id``/``step_id``, via the new :class:`TraceContext` class
  below. ``trace_id``/``span_id`` (real values already exist via the
  OpenTelemetry span context ADR-0017 documents, but wiring that in is
  a distinct, later step — see :mod:`ai_os_kernel.llm_gateway.models`'s
  own note on :class:`TraceContext`) and ``agent_id``/``experiment_id``/
  ``run_id`` (this step's own approved exclusions: no agent metadata,
  no experiment metadata) are deliberately not fields on this reduced
  ``TraceContext`` at all — not present-but-``None``, because an
  always-``None`` field for a capability nothing populates would be
  exactly the "placeholder architecture" this step avoids. Whole-field
  ``metadata: TraceContext | None`` (not the documented contract's
  unconditionally-required ``TraceContext``) so every existing caller
  that never supplies it is completely unaffected.

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

**Excluded from the response:** ``served_from_cache`` (caching),
``degradations`` (capability negotiation), ``raw`` (a debug passthrough
for a real provider payload that does not exist here).
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

    Carries only ``workflow_id``/``step_id`` — the two fields the LLM
    Gateway's Policy & Budget Enforcer needs for a per-workflow cost
    ceiling (llm_gateway.md §9: "Workflow cost ceiling |
    BudgetExceededError"). The other five documented fields are not
    present here at all, by deliberate choice, not oversight:

    - ``trace_id``/``span_id`` (distributed-trace correlation) already
      have real values available today — ADR-0017/observability.md
      document them as propagated via the OpenTelemetry span context
      that this Kernel's own tracing instrumentation already creates
      (``ai_os_kernel.observability.tracing``) — but *reading* that
      context and threading it through here is a distinct, later step
      (Observability integration, not Policy & Budget), so it is left
      out entirely rather than added as a field nothing populates.
    - ``agent_id``/``experiment_id``/``run_id`` are this step's own
      approved exclusions ("no agent metadata, no experiment
      metadata").

    Both this step's own explicit exclusions and the "not yet wired"
    ``trace_id``/``span_id`` are absent as *fields*, not present as
    always-``None`` ones — an always-``None`` field for a capability
    nothing populates would be exactly the "placeholder architecture"
    this step is required to avoid. Adding any of the five once a real
    source exists is a strictly additive, non-breaking change to this
    class, the identical shape every other reduced contract in this
    module already uses.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: str | None = None
    step_id: str | None = None


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
