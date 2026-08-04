"""The minimal LLM Gateway contract: one request in, one response out.

This is a deliberately reduced slice of the full LLM Gateway
(docs/03_architecture/kernel/llm_gateway.md §3), which documents
fourteen internal subsystems (Request Validator, Capability Negotiator,
Policy & Budget Enforcer, Router, Prompt Cache Planner, Provider
Adapters, Retry & Fallback Manager, Rate Limiter, Response Normalizer,
Token & Cost Accountant, Observability, ...). Most of them still do not
sit behind this ``Protocol``: capability negotiation, caching, and
streaming are all out of scope, the same "one Protocol, a small number
of implementations" reduction already applied to
:mod:`ai_os_kernel.workflow_engine.agent`/:mod:`ai_os_kernel.workflow_engine.tool`.
Routing is no longer out of scope either — :class:`DispatchingLLMGateway`
below dispatches by a routing decision rather than always calling the
one gateway it was constructed with, walks that decision's ``fallback``
chain on failure, consults an optional
:class:`~ai_os_kernel.llm_gateway.circuit_breaker.CircuitBreaker` before
each attempt, and retries the same candidate with an optional
:class:`~ai_os_kernel.llm_gateway.backoff.BackoffPolicy` before giving
up on it — all three of §3's named Retry & Fallback Manager pieces
(chain traversal, circuit breaking, backoff) are now real. All three
now also consult the §10 Error Taxonomy
(:mod:`~ai_os_kernel.llm_gateway.error_taxonomy`) on every
:class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`: backoff
retries only a ``retriable`` failure and honours a provider-supplied
``retry_after_seconds``; the Circuit Breaker only counts a
``transient``/``infrastructure`` failure, not a ``permanent`` one; see
that class's own docstring for exactly how. The Policy & Budget
Enforcer's first real slice is also here now — an optional
:class:`~ai_os_kernel.llm_gateway.budget_enforcer.BudgetEnforcer`,
checked before every attempt, ahead of the Circuit Breaker: a
per-``model_alias`` cumulative-cost ceiling reusing the ``cost_usd``
every real adapter already computes, classified ``budget`` — the one
category never gated by chain traversal, since a budget ceiling
applies regardless of which provider would serve the alias. A second,
independent ceiling now also exists, per-``workflow_id``, read from the
request's own :class:`~ai_os_kernel.llm_gateway.models.TraceContext`
(``metadata``) when the caller supplies one; see
:mod:`~ai_os_kernel.llm_gateway.budget_enforcer`'s own docstring for
why this is two independent enforcer instances, not one.

No writer to ``evaluation.llm_calls`` either: Observability is one of
§3's fourteen subsystems, and nothing here produces a real call to
record.

**The Capability Negotiator's matrix lookup is also here now — the
"matrix lookup" half only, not "emulate or fail."**
:class:`DispatchingLLMGateway` gained a new, optional, defaulted-``None``
``capability_negotiator`` and a new public, synchronous
:meth:`DispatchingLLMGateway.capabilities` method answering
platform_sdk.md §5.1's own documented ``capabilities(alias) ->
ProviderCapabilities`` signature. Nothing in :meth:`complete` consults
it — no tool-calling, no structured-output emulation, no streaming, no
``require_capabilities`` field, and no context-window-fit check exist
yet to need it; see :mod:`~ai_os_kernel.llm_gateway.capability_negotiator`'s
own docstring for the full design and the documented discrepancy
between llm_gateway.md §6's and platform_sdk.md §5.1's own field lists.
"""

import asyncio
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import BudgetEnforcer
from ai_os_kernel.llm_gateway.capability_negotiator import (
    CapabilityNegotiator,
    ProviderCapabilities,
)
from ai_os_kernel.llm_gateway.circuit_breaker import CircuitBreaker
from ai_os_kernel.llm_gateway.error_taxonomy import (
    CAPABILITY_UNSUPPORTED,
    CHAIN_EXHAUSTED,
    CIRCUIT_OPEN,
    NO_PROVIDER,
    RATE_LIMIT_EXCEEDED,
    ErrorCategory,
)
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StopReason,
    UsageRecord,
)
from ai_os_kernel.llm_gateway.rate_limiter import RateLimiter
from ai_os_kernel.llm_gateway.router import Router, RoutingDecision

_CIRCUIT_BREAKER_CATEGORIES = (ErrorCategory.TRANSIENT, ErrorCategory.INFRASTRUCTURE)

_ECHO_PROVIDER = "echo"
_ECHO_MODEL_ID = "echo-1"
_ECHO_MODEL_VERSION = "1.0.0"


class LLMGateway(Protocol):
    """The sole seam through which anything in AI_OS may request a model
    completion (ADR-0002). No provider SDK, no adapter, no routing
    behind this Protocol yet — those are later steps."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class TokenCounter(Protocol):
    """A real ``LLMGateway`` implementation that can also answer a
    genuine provider-endpoint token count (llm_gateway.md §12,
    ``P02-S02-M06-T10``) — kept off :class:`LLMGateway` itself, the
    identical "not every implementation can honestly answer this"
    reasoning already applied to keeping ``capabilities()`` off that
    Protocol too. ``@runtime_checkable`` so
    :class:`DispatchingLLMGateway` can ask "does the resolved
    provider's own registered gateway support this?" via
    ``isinstance`` without every :class:`LLMGateway` having to declare
    it, the identical shape :class:`~ai_os_sdk.contracts.agent.Agent`
    already establishes for this exact kind of optional-capability
    check."""

    async def count_tokens(self, request: LLMRequest) -> int: ...


@runtime_checkable
class Embedder(Protocol):
    """A real ``LLMGateway`` implementation that can also answer a
    genuine provider-endpoint embedding call (llm_gateway.md §11,
    ``P02-S02-M06-T09``) — kept off :class:`LLMGateway` itself, the
    identical reasoning :class:`TokenCounter` already applies:
    Anthropic's own real API has no embeddings endpoint at all, so
    forcing every :class:`LLMGateway` to declare ``embed()`` would ship
    a method the primary registered adapter must always raise from.
    ``@runtime_checkable`` for the identical reason :class:`TokenCounter`
    already is."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


class EchoLLMGateway:
    """The one trivial in-process implementation for this step.

    Calls no provider, performs no routing, and never will need to for
    what it does — it exists to prove the request/response contract
    works end to end, mirroring ``EchoAgent``/``EchoTool``'s "always
    succeeds, does no real work" role.

    "Completion" is a literal echo of the conversation's last message,
    deterministic and inspectable. ``max_output_tokens`` genuinely
    bounds the result — using character count as a stand-in for a real
    token count, since no real tokenizer exists here and §12 forbids
    approximating one for actual accounting ("a third-party or
    foreign-provider tokenizer is never used ... an approximation would
    corrupt both budget enforcement and cost reporting"). This is a
    length cap proving the field has real effect, not a token-accurate
    implementation — which is also why ``usage.input_tokens``/
    ``output_tokens`` stay honestly ``0`` rather than reporting the same
    character count as if it meant something it does not.
    """

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()

        full_content = request.messages[-1].content
        truncated = len(full_content) > request.max_output_tokens
        content = full_content[: request.max_output_tokens] if truncated else full_content
        stop_reason = StopReason.MAX_TOKENS if truncated else StopReason.END_TURN

        latency_ms = int((time.monotonic() - started) * 1000)

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=UsageRecord(
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=latency_ms,
                provider=_ECHO_PROVIDER,
                model_id=_ECHO_MODEL_ID,
                retries=0,
                fallback_used=False,
            ),
            provider=_ECHO_PROVIDER,
            model_id=_ECHO_MODEL_ID,
            model_version=_ECHO_MODEL_VERSION,
        )


class DispatchingLLMGateway:
    """The real multi-provider :class:`LLMGateway`, and now all three of
    the Retry & Fallback Manager's named pieces (llm_gateway.md §3:
    "backoff, circuit breaker, chain traversal"): asks the injected
    :class:`~ai_os_kernel.llm_gateway.router.Router` which provider a
    request's ``model_alias`` currently means, skips straight to the
    next candidate if the optional :class:`~ai_os_kernel.llm_gateway.
    circuit_breaker.CircuitBreaker` reports that provider unavailable,
    otherwise delegates the *unmodified* request to that provider's own
    real ``LLMGateway`` implementation — retrying that same candidate
    per the optional :class:`~ai_os_kernel.llm_gateway.backoff.BackoffPolicy`
    before giving up on it — and reports each real attempt's outcome
    back to the breaker. Either way, if every retry of a candidate is
    exhausted and it still raises
    :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`, this
    tries the resolved decision's ``fallback``, and its own
    ``fallback``, and so on, until one succeeds or the chain is
    exhausted.

    "Keep all routing decisions encapsulated inside the Router
    abstraction" (an earlier step's own approved framing, still true
    here): every candidate tried here is a link the Router's own
    resolved :class:`~ai_os_kernel.llm_gateway.router.RoutingDecision`
    chain already named — this class never invents, reorders, or scores
    a candidate; it only walks the chain the Router built, skipping a
    candidate the breaker reports unavailable rather than trying it, and
    retrying a candidate before moving past it rather than moving past
    it immediately. No provider health beyond the breaker's own binary
    available/unavailable signal, no experiment pinning — this step's
    own approved exclusions.

    ``backoff_policy`` defaults to ``None`` — "not triggered," in this
    step's own terms: every existing caller that never passes it (every
    test and composition written before this step) gets byte-for-byte
    the identical single-attempt-per-candidate behaviour as before, and
    a policy that *is* supplied changes nothing observable for a
    candidate that succeeds on its first attempt either — no delay is
    ever inserted unless a real failure actually needs retrying (this
    step's own "preserve existing behaviour when backoff is not
    triggered" requirement). **Backoff and the circuit breaker cooperate
    directly, not just side by side**: before sleeping for a retry, the
    breaker (if any) is consulted again — if the *first* attempt's
    failure already opened the circuit, no further retry of that same,
    now-known-unhealthy candidate is attempted (and no delay is spent
    on one either), the chain moves straight to the next fallback
    instead. A response that only succeeded after one or more retries
    has its ``usage.retries`` honestly set to the number of retries that
    preceded the success — llm_gateway.md §5's own field, previously
    always ``0`` because no real retry existed yet to count. **A retry
    is now also gated by the Error Taxonomy**
    (:mod:`~ai_os_kernel.llm_gateway.error_taxonomy`): a failure
    classified ``retriable=False`` (an invalid request, an unsupported
    capability, ...) is never retried — this candidate is abandoned
    immediately in favour of the fallback, since a delay would only
    ever reproduce the identical, still-permanent failure. When a
    failure does carry a provider-supplied ``retry_after_seconds`` (a
    rate limit's own wait hint), that value is honoured — the actual
    delay is whichever of the policy's own computed delay and the
    provider's hint is larger, never less than what the provider asked
    for.

    ``rate_limiter`` (``P02-S02-M06-T11``) defaults to ``None`` — the
    identical "absent means disabled, zero observable change" shape
    every other optional collaborator here already uses. When
    supplied, it is consulted right after the two budget checks and
    before the Circuit Breaker: a proactive, per-provider request-
    volume gate (llm_gateway.md §9's own "respect per-provider rate
    limits proactively"), distinct from and checked earlier than the
    Circuit Breaker's own reactive, failure-driven gate. A rejection is
    classified :data:`~ai_os_kernel.llm_gateway.error_taxonomy.RATE_LIMIT_EXCEEDED`
    (``transient``, retriable) with a real ``retry_after_seconds``
    computed from the limiter's own window countdown — honoured by
    :meth:`_call_with_backoff` exactly like a real provider's own
    ``Retry-After`` hint, and, with no ``backoff_policy`` configured,
    triggers the identical fallback-chain traversal any other
    provider-scoped failure already does (unlike a budget failure,
    a rate limit is scoped to *this* provider, so trying the next
    candidate in the chain is a real, useful escape, not futile). A
    rate-limit rejection never calls ``circuit_breaker.record_failure``
    — no real network call was attempted, so there is nothing new to
    remember about this provider's own health.

    ``circuit_breaker`` defaults to ``None`` — "disabled," in this
    step's own terms: every existing caller that never passes it (every
    test and composition written before this step) gets byte-for-byte
    the identical chain-traversal-only behaviour as before, since the
    breaker is only ever consulted when one is actually supplied.
    Passing one also changes nothing observable *until a provider
    actually opens* — ``is_available()`` returns ``True`` for a
    provider it has no failure memory for, so a healthy chain runs
    exactly as it always did (this step's own "preserve existing
    behaviour when Circuit Breakers are disabled or no provider has
    transitioned to an open state" requirement). **Only a
    ``transient``/``infrastructure`` failure now counts toward the
    breaker** — a ``permanent`` failure (the caller's own malformed
    request, an unsupported capability) is not evidence this
    *provider* is unhealthy, so it no longer opens the circuit; every
    :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError` that
    does not carry an explicit classification still defaults to
    ``transient`` (this class's own pre-Error-Taxonomy behaviour,
    unchanged for anything not explicitly reclassified).

    ``budget_enforcer``/``workflow_budget_enforcer`` both default to
    ``None`` — the identical "disabled, no observable change" shape
    ``circuit_breaker`` and ``backoff_policy`` already use. When
    supplied, both are consulted *first*, ahead of the Circuit Breaker
    — a policy/budget gate takes priority over a resilience mechanism,
    since there is no point checking whether a provider is healthy for
    a call that should never be attempted at all. ``budget_enforcer``
    is scoped by ``request.model_alias`` (present on every request
    since the Router itself was built); ``workflow_budget_enforcer`` is
    scoped by ``request.metadata.workflow_id`` when the caller supplies
    a :class:`~ai_os_kernel.llm_gateway.models.TraceContext` with one —
    see :mod:`~ai_os_kernel.llm_gateway.budget_enforcer`'s own docstring
    for why these are two independent instances/ceilings, not one. A
    request with no ``metadata``, or ``metadata`` with no
    ``workflow_id``, simply cannot be checked against the workflow
    ceiling — there is nothing to key by, so it is skipped, not an
    error (this step's own "preserve existing behaviour for callers
    that do not use the new metadata" requirement; every caller before
    this step never set ``metadata``, so every one of them is
    unaffected). Every real success reports its honest ``usage.cost_usd``
    back to whichever of the two enforcers could be checked. A budget
    failure (from either enforcer) is classified ``ErrorCategory.BUDGET``
    and — unlike every other category — **never triggers a fallback
    attempt**: the check in :meth:`complete` treats it as a special
    case, because a budget ceiling (alias- or workflow-scoped) is never
    scoped to any one provider, so every candidate in the chain would
    share the identical verdict — trying another provider can never be
    the fix a caller needs.

    An alias with **no configured fallback behaves exactly as before**:
    a single failed call raises the adapter's own
    :class:`LLMProviderError` completely unchanged, byte-for-byte the
    same as every existing test already asserts (this step's own
    "preserve deterministic behaviour when no fallback chain is
    configured" requirement). A resolved provider with no registered
    gateway, and now also a resolved provider whose circuit is
    ``OPEN``, are both treated as one more failure in the chain, not a
    special case: each raises its own clear ``LLMProviderError``, which
    either propagates (no fallback) or triggers the next candidate (a
    fallback exists) — the same uniform treatment every other failure
    gets. A circuit-open skip never calls the breaker's own
    ``record_failure`` — no real call was attempted, so there is
    nothing new to remember.

    A response that only succeeded on a fallback candidate has its
    ``usage.fallback_used`` honestly set to ``True`` before being
    returned — the field llm_gateway.md §5 already documents for
    exactly this, previously always ``False`` because no real fallback
    existed yet to set it. Falling all the way through every candidate
    raises one clear, aggregate ``LLMProviderError`` naming every
    provider tried, chaining the last underlying error via ``from`` —
    classified exactly as llm_gateway.md §10's own table names it:
    ``transient``/``llm.chain_exhausted``/retriable ("All providers in
    chain failed | transient | llm.chain_exhausted | Yes, with
    backoff").

    :class:`~ai_os_kernel.llm_gateway.errors.LLMRefusalError` (the
    model's own safety classifiers declining the request) is
    deliberately **not** caught here and never triggers a fallback — a
    refusal is a real, valid response llm_gateway.md §5 documents as
    distinct from a failure, not a fault to route around; silently
    trying a different provider on a refusal would be a real behaviour
    decision this step's approved framing does not ask for.

    ``gateways`` may hold any real :class:`LLMGateway` implementation
    under any provider name a :class:`~ai_os_kernel.llm_gateway.router.
    Router` might resolve to — :class:`~ai_os_kernel.llm_gateway.
    adapters.anthropic_adapter.AnthropicAdapter` and
    :class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`
    are the two real, network-calling providers registered in the real
    composition root (``kernel/bootstrap.py``); :class:`EchoLLMGateway`
    remains useful in tests as a third, already-real implementation
    that needs no network at all.

    ``capability_negotiator`` defaults to ``None`` too, but unlike
    every collaborator above, it is never consulted by :meth:`complete`
    itself — this step builds the Capability Negotiator's matrix lookup
    only (llm_gateway.md §6's "matrix lookup" half, not its "emulate or
    fail" half), so nothing in the completion path yet has a reason to
    ask it anything. It backs the separate, synchronous
    :meth:`capabilities` method instead — a real fact-lookup a caller
    may use independently of making a request at all, mirroring
    platform_sdk.md §5.1's own ``capabilities(alias) -> ProviderCapabilities``
    signature exactly (not ``async``, since answering it needs no I/O:
    the matrix is already-loaded configuration).
    """

    def __init__(
        self,
        *,
        router: Router,
        gateways: Mapping[str, LLMGateway],
        circuit_breaker: CircuitBreaker | None = None,
        backoff_policy: BackoffPolicy | None = None,
        budget_enforcer: BudgetEnforcer | None = None,
        workflow_budget_enforcer: BudgetEnforcer | None = None,
        capability_negotiator: CapabilityNegotiator | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._router = router
        self._gateways = dict(gateways)
        self._circuit_breaker = circuit_breaker
        self._backoff_policy = backoff_policy
        self._budget_enforcer = budget_enforcer
        self._workflow_budget_enforcer = workflow_budget_enforcer
        self._capability_negotiator = capability_negotiator
        self._rate_limiter = rate_limiter

    def capabilities(self, model_alias: str) -> ProviderCapabilities:
        """The Capability Negotiator's own documented lookup
        (llm_gateway.md §6, platform_sdk.md §5.1) — a synchronous,
        no-I/O fact lookup, unlike :meth:`complete`. Raises
        :class:`LLMProviderError` (``llm.no_capability_negotiator``,
        matching the shape every other "not configured" condition in
        this class already uses) when no negotiator was supplied —
        deliberately not a silent default, since there is no safe
        "unknown capabilities" matrix to fabricate the way an absent
        ``budget_enforcer`` safely means "no limit."
        """
        if self._capability_negotiator is None:
            raise LLMProviderError(
                "no CapabilityNegotiator configured for this gateway — "
                "capabilities() cannot answer without one",
                category=ErrorCategory.PERMANENT,
                error_code="llm.no_capability_negotiator",
                retriable=False,
            )
        return self._capability_negotiator.capabilities(model_alias)

    async def count_tokens(self, request: LLMRequest) -> int:
        """A real, exact provider-endpoint token count
        (llm_gateway.md §12, ``P02-S02-M06-T10``) — never a
        character-length or third-party-tokenizer approximation.

        Resolves ``request.model_alias`` exactly once, the same
        :class:`~ai_os_kernel.llm_gateway.router.Router` call
        :meth:`complete` makes, then asks *only* that one resolved
        candidate's registered :class:`LLMGateway` — never its
        ``fallback``. A token count is specific to one real model's own
        tokenizer; silently reporting a different provider's count
        would be a real, wrong answer for the model actually named,
        not an honest substitute for it (llm_gateway.md §12's own "no
        approximation" rule applies just as much to "the wrong
        provider's exact count" as to a heuristic one).

        Raises :class:`LLMProviderError`
        (:data:`~ai_os_kernel.llm_gateway.error_taxonomy.CAPABILITY_UNSUPPORTED`)
        when the resolved provider has no registered gateway at all, or
        when its registered gateway does not implement
        :class:`TokenCounter` — deliberately not a silent ``0`` or a
        fabricated estimate.
        """
        decision = self._router.resolve(request.model_alias)
        gateway = self._gateways.get(decision.provider)
        if gateway is None or not isinstance(gateway, TokenCounter):
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, which does not support a real "
                "provider-endpoint token count",
                category=CAPABILITY_UNSUPPORTED.category,
                error_code=CAPABILITY_UNSUPPORTED.error_code,
                retriable=CAPABILITY_UNSUPPORTED.retriable,
            )
        return await gateway.count_tokens(request)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """A real, provider-endpoint embedding call (llm_gateway.md
        §11, ``P02-S02-M06-T09``) — never a fabricated or hashed
        stand-in vector.

        Resolves ``request.model_alias`` exactly once, the identical
        shape :meth:`count_tokens` already establishes, then asks
        *only* that one resolved candidate's registered
        :class:`LLMGateway` — never its ``fallback``. §11: "queries
        only compare vectors from the same model and version" — a
        fallback provider's embedding model lives in a genuinely
        different vector space, so silently substituting one would be
        a real, wrong answer, not a valid alternative the way a
        fallback chat completion is.

        Raises :class:`LLMProviderError`
        (:data:`~ai_os_kernel.llm_gateway.error_taxonomy.CAPABILITY_UNSUPPORTED`)
        when the resolved provider has no registered gateway at all, or
        when its registered gateway does not implement
        :class:`Embedder` — every existing provider today except
        ``local`` (Anthropic's own real API has no embeddings endpoint
        to call).
        """
        decision = self._router.resolve(request.model_alias)
        gateway = self._gateways.get(decision.provider)
        if gateway is None or not isinstance(gateway, Embedder):
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, which does not support real "
                "provider-endpoint embeddings",
                category=CAPABILITY_UNSUPPORTED.category,
                error_code=CAPABILITY_UNSUPPORTED.error_code,
                retriable=CAPABILITY_UNSUPPORTED.retriable,
            )
        return await gateway.embed(request)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        decision = self._router.resolve(request.model_alias)
        attempted_providers: list[str] = []
        used_fallback = False

        while True:
            attempted_providers.append(decision.provider)
            try:
                response = await self._call_with_backoff(decision, request)
            except LLMProviderError as exc:
                if exc.category == ErrorCategory.BUDGET:
                    # A budget ceiling is scoped to the caller's alias,
                    # not to any one provider — every candidate in the
                    # chain shares the identical verdict, so falling
                    # back can never escape it. Raise immediately,
                    # unwrapped, rather than exhausting a chain that
                    # was never going to help.
                    raise
                if decision.fallback is None:
                    if not used_fallback:
                        raise
                    raise LLMProviderError(
                        f"model_alias {request.model_alias!r}: every candidate in the "
                        f"fallback chain failed ({' -> '.join(attempted_providers)}); "
                        f"last error: {exc}",
                        category=CHAIN_EXHAUSTED.category,
                        error_code=CHAIN_EXHAUSTED.error_code,
                        retriable=CHAIN_EXHAUSTED.retriable,
                    ) from exc
                decision = decision.fallback
                used_fallback = True
                continue

            if used_fallback:
                response = response.model_copy(
                    update={"usage": response.usage.model_copy(update={"fallback_used": True})}
                )
            return response

    async def _call_with_backoff(
        self, decision: RoutingDecision, request: LLMRequest
    ) -> LLMResponse:
        if self._backoff_policy is None:
            return await self._call(decision, request)

        policy = self._backoff_policy
        started = time.monotonic()
        retry_number = 1

        while True:
            try:
                response = await self._call(decision, request)
            except LLMProviderError as exc:
                if not exc.retriable:
                    # The Error Taxonomy classified this failure as not
                    # worth retrying — the caller's own request, not a
                    # transient condition of this candidate. Give up on
                    # this candidate immediately (chain traversal may
                    # still try the next one); a delay would only ever
                    # produce the identical, still-permanent failure.
                    raise
                if retry_number >= policy.max_attempts:
                    raise
                if self._circuit_breaker is not None and not self._circuit_breaker.is_available(
                    decision.provider
                ):
                    # The failure just recorded already opened this
                    # candidate's circuit — a further retry would be
                    # rejected before ever reaching the network, so
                    # there is nothing to gain from also spending a
                    # delay on it. Move on to the fallback instead.
                    raise
                delay = policy.delay_seconds(retry_number)
                if exc.retry_after_seconds is not None:
                    # Honour a provider-supplied wait hint (e.g. a
                    # rate limit's Retry-After) over this policy's own
                    # computed delay when the provider asked for more.
                    delay = max(delay, exc.retry_after_seconds)
                if time.monotonic() - started + delay > policy.max_total_seconds:
                    raise
                await asyncio.sleep(delay)
                retry_number += 1
                continue

            if retry_number > 1:
                response = response.model_copy(
                    update={
                        "usage": response.usage.model_copy(update={"retries": retry_number - 1})
                    }
                )
            return response

    async def _call(self, decision: RoutingDecision, request: LLMRequest) -> LLMResponse:
        if self._budget_enforcer is not None and not self._budget_enforcer.is_within_budget(
            request.model_alias
        ):
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} has exceeded its configured budget "
                "ceiling — no further calls are permitted for this alias",
                category=ErrorCategory.BUDGET,
                error_code="llm.budget_exceeded",
                retriable=False,
            )

        workflow_id = request.metadata.workflow_id if request.metadata is not None else None
        if (
            self._workflow_budget_enforcer is not None
            and workflow_id is not None
            and not self._workflow_budget_enforcer.is_within_budget(workflow_id)
        ):
            raise LLMProviderError(
                f"workflow {workflow_id!r} has exceeded its configured budget ceiling — "
                "no further calls are permitted for this workflow",
                category=ErrorCategory.BUDGET,
                error_code="llm.budget_exceeded",
                retriable=False,
            )

        if self._rate_limiter is not None:
            rate_limit_result = await self._rate_limiter.check(decision.provider)
            if not rate_limit_result.allowed:
                raise LLMProviderError(
                    f"model_alias {request.model_alias!r} routes to provider "
                    f"{decision.provider!r}, which has exceeded its configured "
                    "rate limit — no further calls are permitted this window",
                    category=RATE_LIMIT_EXCEEDED.category,
                    error_code=RATE_LIMIT_EXCEEDED.error_code,
                    retriable=RATE_LIMIT_EXCEEDED.retriable,
                    retry_after_seconds=rate_limit_result.retry_after_seconds,
                )

        if self._circuit_breaker is not None and not self._circuit_breaker.is_available(
            decision.provider
        ):
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, whose circuit breaker is currently open "
                "(too many recent consecutive failures)",
                category=CIRCUIT_OPEN.category,
                error_code=CIRCUIT_OPEN.error_code,
                retriable=CIRCUIT_OPEN.retriable,
            )

        gateway = self._gateways.get(decision.provider)
        if gateway is None:
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, which has no registered LLMGateway "
                f"(registered: {sorted(self._gateways)})",
                category=NO_PROVIDER.category,
                error_code=NO_PROVIDER.error_code,
                retriable=NO_PROVIDER.retriable,
            )

        try:
            response = await gateway.complete(request)
        except LLMProviderError as exc:
            # Only a transient/infrastructure failure is real evidence
            # this *provider* is unhealthy — a permanent failure (an
            # invalid request, an unsupported capability) is the
            # caller's problem, and counting it would let a client
            # sending malformed requests wrongly trip a circuit that
            # would otherwise serve every other, valid request fine.
            if self._circuit_breaker is not None and exc.category in _CIRCUIT_BREAKER_CATEGORIES:
                self._circuit_breaker.record_failure(decision.provider)
            raise

        if self._circuit_breaker is not None:
            self._circuit_breaker.record_success(decision.provider)
        if self._budget_enforcer is not None:
            self._budget_enforcer.record_spend(request.model_alias, response.usage.cost_usd)
        if self._workflow_budget_enforcer is not None and workflow_id is not None:
            self._workflow_budget_enforcer.record_spend(workflow_id, response.usage.cost_usd)
        return response
