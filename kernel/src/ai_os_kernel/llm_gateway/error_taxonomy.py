"""The LLM Gateway's Error Taxonomy (llm_gateway.md §10).

**"There is no second, Gateway-specific taxonomy"** — the platform's
single error taxonomy lives in
``docs/03_architecture/workflow/error_handling_retry.md`` §3, and every
component, including the LLM Gateway, maps into it. That document's own
history is instructive: its v1.0 defined four categories while
llm_gateway.md defined six unrelated ones with no mapping between them;
the two documents were reconciled into one unified six-category set
(``transient``, ``permanent``, ``quality``, ``infrastructure``,
``budget``, ``security``). :class:`ErrorCategory` below carries only
the **four** of those six a provider call failure can ever actually be
— ``quality`` (Quality Gate findings) and ``security`` (authorization/
policy denials) do not describe anything an LLM provider call can
raise. This module does not build the platform-wide ``AiOsError``
exception hierarchy error_handling_retry.md §8 describes (``AiOsError``
-> ``TransientError``, ``PermanentError``, ``QualityError``,
``InfrastructureError``, ``BudgetExceededError``, ``SecurityError``) —
that hierarchy does not exist anywhere in this codebase yet, and
building it would mean reaching into the Workflow Engine, Quality Gate
Engine, and Security Manager, all explicitly out of scope for a step
scoped to "keep error classification encapsulated inside the LLM
Gateway." Instead, :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`
itself carries ``category``/``error_code``/``retriable``/
``retry_after_seconds`` fields, using the exact vocabulary and field
names error_handling_retry.md §8's ``StructuredError`` documents, so a
future platform-wide adoption is a natural migration, not a rewrite.

**``retriable`` answers one specific question**: is retrying the
*identical* call, against the *same* provider candidate, worth
attempting? It does not answer whether a *different* candidate in a
fallback chain might succeed — a provider-specific auth failure or an
invalid-request error is often provider-specific (a different
provider's formatting requirements, or a larger context window, may
not have the same problem), so
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` still
walks the fallback chain on *any* :class:`~ai_os_kernel.llm_gateway.
errors.LLMProviderError` regardless of ``retriable`` — only
same-candidate backoff retry is gated by it.

**Only ``transient``/``infrastructure`` failures count toward the
Circuit Breaker.** A ``permanent`` failure (an invalid request, an
unsupported capability) is the caller's problem, not evidence the
provider itself is unhealthy — counting it would let a client sending
malformed requests wrongly trip a circuit that would otherwise serve
every other, valid request just fine. ``infrastructure`` (e.g. an auth
failure) *does* count: repeated authentication failures are a real
signal something about this provider's configuration is broken.

**Every default matches today's undifferentiated behaviour exactly.**
:class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`'s
``category``/``retriable`` default to ``ErrorCategory.TRANSIENT``/
``True`` — identical to what every pre-existing call site (and every
pre-existing test constructing a bare ``LLMProviderError("message")``)
already assumed before this step: retried by backoff, counted by the
Circuit Breaker. Only call sites this step explicitly updates classify
differently; everything else is unaffected — this step's own "preserve
existing behaviour where no explicit classification applies"
requirement.

**``retry_after`` is honoured, to the extent a value is available.**
Neither adapter extracted a ``Retry-After`` value before this step;
:func:`parse_retry_after_seconds` reads the header's numeric-seconds
form (the common case for rate limiting). The HTTP-date form
(``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT``) is a real, documented
gap, not parsed here — a provider using that form degrades to this
Gateway's own computed exponential-backoff delay instead, an honest
fallback, not a crash.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class ErrorCategory(StrEnum):
    """The four of error_handling_retry.md §3's six platform-wide
    categories a provider call failure can ever actually be — see this
    module's own docstring for why ``quality``/``security`` are
    excluded."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    INFRASTRUCTURE = "infrastructure"
    BUDGET = "budget"


class ErrorClassification(NamedTuple):
    """One resolved classification: a category, an ``error_code``
    (llm_gateway.md §10's own catalogue, extended with a small number
    of Gateway-internal codes §10 does not name — misconfiguration and
    circuit-breaker conditions are not provider conditions), and
    whether retrying the identical call is worth attempting."""

    category: ErrorCategory
    error_code: str
    retriable: bool


# The non-HTTP-status classifications llm_gateway.md §10's table names
# directly, plus the small number of Gateway-internal conditions (not
# provider conditions) the table does not cover.
NETWORK_FAILURE = ErrorClassification(ErrorCategory.TRANSIENT, "llm.network", True)
CAPABILITY_UNSUPPORTED = ErrorClassification(
    ErrorCategory.PERMANENT, "llm.capability_unsupported", False
)
CHAIN_EXHAUSTED = ErrorClassification(ErrorCategory.TRANSIENT, "llm.chain_exhausted", True)
CIRCUIT_OPEN = ErrorClassification(ErrorCategory.TRANSIENT, "llm.circuit_open", True)
NO_ROUTE = ErrorClassification(ErrorCategory.PERMANENT, "llm.no_route", False)
NO_PROVIDER = ErrorClassification(ErrorCategory.PERMANENT, "llm.no_provider", False)
MISROUTED = ErrorClassification(ErrorCategory.PERMANENT, "llm.misrouted", False)
NO_PRICING = ErrorClassification(ErrorCategory.PERMANENT, "llm.no_pricing", False)
NO_CAPABILITIES = ErrorClassification(ErrorCategory.PERMANENT, "llm.no_capabilities", False)
UNPARSEABLE_RESPONSE = ErrorClassification(ErrorCategory.TRANSIENT, "llm.provider_error", True)


def classify_http_status(status_code: int) -> ErrorClassification:
    """Maps an HTTP status code a provider actually returned onto
    llm_gateway.md §10's table.

    Status codes the table does not name explicitly fall back to a
    safe default by range: any other 5xx is treated the same as the
    documented "Server error (5xx)" (transient, retriable — the
    provider's problem, worth at least one more attempt); any other
    4xx is treated the same as the documented "Invalid request (400)"
    (permanent, not retriable — the caller's problem, never worth
    retrying unmodified).
    """

    if status_code == 429:
        return ErrorClassification(ErrorCategory.TRANSIENT, "llm.rate_limited", True)
    if status_code == 529:
        return ErrorClassification(ErrorCategory.TRANSIENT, "llm.overloaded", True)
    if status_code in (401, 403):
        return ErrorClassification(ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False)
    if status_code >= 500:
        return ErrorClassification(ErrorCategory.TRANSIENT, "llm.provider_error", True)
    return ErrorClassification(ErrorCategory.PERMANENT, "llm.invalid_request", False)


def parse_retry_after_seconds(value: str | None) -> float | None:
    """Parses a ``Retry-After`` header's numeric-seconds form. Returns
    ``None`` for a missing header or the HTTP-date form — see this
    module's own docstring for why the date form is a real, documented
    gap rather than a crash.
    """

    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
