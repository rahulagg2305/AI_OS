"""Unit tests for the Router's first real multi-provider consumer
(ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway): dispatches a
request to the correct registered ``LLMGateway`` by asking the Router
which provider the request's ``model_alias`` currently means — no
network, no I/O, using two already-real ``LLMGateway`` implementations
(``EchoLLMGateway`` twice, distinguishable only by which one a given
alias resolves to, is enough to prove genuine dispatch without a second
network-calling adapter).
"""

import asyncio
import time
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import (
    PerScopeBudgetEnforcer,
    PerScopeCountBudgetEnforcer,
)
from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities,
    StaticCapabilityNegotiator,
)
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError, LLMRefusalError
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    Message,
    MessageRole,
    StreamEventType,
    TraceContext,
    UsageRecord,
)
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter, build_routing_chain


def _request(
    model_alias: str, workflow_id: str | None = None, step_id: str | None = None
) -> LLMRequest:
    metadata = (
        TraceContext(workflow_id=workflow_id, step_id=step_id)
        if workflow_id is not None or step_id is not None
        else None
    )
    return LLMRequest(
        model_alias=model_alias,
        messages=[Message(role=MessageRole.USER, content="hello")],
        max_output_tokens=16,
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_dispatches_to_the_registered_gateway_the_router_names() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    gateway_a = EchoLLMGateway()
    gateway_b = EchoLLMGateway()
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": gateway_a, "provider-b": gateway_b}
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"


@pytest.mark.asyncio
async def test_two_aliases_genuinely_reach_two_different_registered_gateways() -> None:
    # The specific capability this step adds: one DispatchingLLMGateway
    # instance routing different aliases to genuinely different
    # LLMGateway objects, not always the same one.
    router = StaticRouter(
        routes={
            "alias-a": RoutingDecision(provider="provider-a", model_id="model-a"),
            "alias-b": RoutingDecision(provider="provider-b", model_id="model-b"),
        }
    )
    calls: list[str] = []

    class _RecordingGateway:
        def __init__(self, name: str) -> None:
            self._name = name

        async def complete(self, request: LLMRequest) -> LLMResponse:
            calls.append(self._name)
            return await EchoLLMGateway().complete(request)

    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _RecordingGateway("a"), "provider-b": _RecordingGateway("b")},
    )

    await dispatcher.complete(_request("alias-a"))
    await dispatcher.complete(_request("alias-b"))

    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_raises_clearly_when_the_resolved_provider_has_no_registered_gateway() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="unregistered-provider", model_id="x")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError, match="no registered LLMGateway"):
        await dispatcher.complete(_request("fast-cheap"))


@pytest.mark.asyncio
async def test_raises_clearly_for_an_alias_the_router_does_not_know() -> None:
    router = StaticRouter(routes={})
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError, match="no configured route"):
        await dispatcher.complete(_request("does-not-exist"))


# --- Retry & Fallback Manager: chain traversal ------------------------


class _FailingGateway:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise self._error


@pytest.mark.asyncio
async def test_falls_back_to_the_next_candidate_when_the_primary_fails() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(LLMProviderError("provider-a is down")),
            "provider-b": EchoLLMGateway(),
        },
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"
    assert response.usage.fallback_used is True


@pytest.mark.asyncio
async def test_does_not_mark_fallback_used_when_the_primary_succeeds() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": EchoLLMGateway(), "provider-b": EchoLLMGateway()},
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.usage.fallback_used is False


@pytest.mark.asyncio
async def test_raises_the_original_error_unchanged_when_no_fallback_is_configured() -> None:
    # This step's own "preserve deterministic behaviour when no fallback
    # chain is configured" requirement: a single-candidate alias must
    # raise the exact same error as before this feature existed.
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    original_error = LLMProviderError("provider-a is down")
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FailingGateway(original_error)}
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap"))

    assert exc_info.value is original_error


@pytest.mark.asyncio
async def test_raises_a_clear_aggregate_error_when_every_candidate_in_the_chain_fails() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(LLMProviderError("provider-a is down")),
            "provider-b": _FailingGateway(LLMProviderError("provider-b is down")),
        },
    )

    with pytest.raises(LLMProviderError, match="every candidate in the fallback chain failed"):
        await dispatcher.complete(_request("fast-cheap"))


@pytest.mark.asyncio
async def test_a_missing_gateway_registration_triggers_fallback_like_any_other_failure() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-b": EchoLLMGateway()}
    )  # "provider-a" is not registered at all

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.usage.fallback_used is True


@pytest.mark.asyncio
async def test_a_refusal_is_not_caught_and_never_triggers_a_fallback() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(LLMRefusalError("the model declined")),
            "provider-b": EchoLLMGateway(),
        },
    )

    with pytest.raises(LLMRefusalError):
        await dispatcher.complete(_request("fast-cheap"))


# --- Retry & Fallback Manager: circuit breaker cooperation -------------


class _UnreachableGateway:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise AssertionError("this gateway must not be called while its circuit is open")


class _RecordingCircuitBreaker:
    """A test double implementing the ``CircuitBreaker`` Protocol,
    recording every call so a test can assert exactly what the
    dispatcher did and did not do — not the real, timer-based
    ``InMemoryCircuitBreaker`` (that class has its own dedicated tests
    in ``test_circuit_breaker.py``)."""

    def __init__(self, *, unavailable: set[str] | None = None) -> None:
        self._unavailable = unavailable or set()
        self.calls: list[str] = []

    def is_available(self, provider: str) -> bool:
        self.calls.append(f"is_available:{provider}")
        return provider not in self._unavailable

    def record_success(self, provider: str) -> None:
        self.calls.append(f"success:{provider}")

    def record_failure(self, provider: str) -> None:
        self.calls.append(f"failure:{provider}")


@pytest.mark.asyncio
async def test_skips_a_candidate_whose_circuit_is_open_without_calling_its_gateway() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    breaker = _RecordingCircuitBreaker(unavailable={"provider-a"})
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _UnreachableGateway(), "provider-b": EchoLLMGateway()},
        circuit_breaker=breaker,
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.usage.fallback_used is True
    # A skip is not a recorded failure — no real call was attempted.
    assert "failure:provider-a" not in breaker.calls
    assert "success:provider-b" in breaker.calls


@pytest.mark.asyncio
async def test_records_success_after_a_real_successful_call() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    breaker = _RecordingCircuitBreaker()
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": EchoLLMGateway()}, circuit_breaker=breaker
    )

    await dispatcher.complete(_request("fast-cheap"))

    assert breaker.calls == ["is_available:provider-a", "success:provider-a"]


@pytest.mark.asyncio
async def test_records_failure_after_a_real_failed_call() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    breaker = _RecordingCircuitBreaker()
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _FailingGateway(LLMProviderError("provider-a is down"))},
        circuit_breaker=breaker,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    assert breaker.calls == ["is_available:provider-a", "failure:provider-a"]


@pytest.mark.asyncio
async def test_a_real_circuit_breaker_skips_an_open_provider_on_a_later_call() -> None:
    # End-to-end: the real, timer-based InMemoryCircuitBreaker actually
    # opens after a real failure, and DispatchingLLMGateway actually
    # respects that on the very next call — not a spy, the real class.
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    breaker = InMemoryCircuitBreaker(failure_threshold=1, reset_timeout_seconds=30.0)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(LLMProviderError("provider-a is down")),
            "provider-b": EchoLLMGateway(),
        },
        circuit_breaker=breaker,
    )

    first = await dispatcher.complete(_request("fast-cheap"))
    assert first.usage.fallback_used is True
    assert breaker.is_available("provider-a") is False

    # provider-a's circuit is now open: swap in a gateway that raises if
    # ever called, proving the dispatcher skips straight past it.
    dispatcher._gateways["provider-a"] = _UnreachableGateway()
    second = await dispatcher.complete(_request("fast-cheap"))
    assert second.usage.fallback_used is True


# --- Retry & Fallback Manager: backoff ---------------------------------


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every backoff test below uses a real BackoffPolicy, which computes
    # a real (small, jittered) delay. Making asyncio.sleep a no-op keeps
    # the suite fast without changing the retry-count/timing-budget
    # logic under test — every assertion is about *how many* attempts
    # were made and *what* the response says, never about wall-clock
    # duration.
    async def _instant_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _policy(
    *, max_attempts: int = 3, max_total_seconds: float = 5.0, base_delay_seconds: float = 0.1
) -> BackoffPolicy:
    return BackoffPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=1.0,
        max_total_seconds=max_total_seconds,
    )


class _FailNTimesGateway:
    """Fails its first ``fail_count`` calls with ``error``, then
    delegates to a real ``EchoLLMGateway`` — a stand-in for "the network
    call fails a couple of times, then the provider recovers."""

    def __init__(self, *, fail_count: int, error: Exception) -> None:
        self._remaining_failures = fail_count
        self._error = error
        self.call_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise self._error
        return await EchoLLMGateway().complete(request)


@pytest.mark.asyncio
async def test_no_backoff_policy_configured_makes_exactly_one_attempt() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    gateway = _FailNTimesGateway(fail_count=1, error=LLMProviderError("down"))
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": gateway})

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    assert gateway.call_count == 1


@pytest.mark.asyncio
async def test_a_successful_first_attempt_needs_no_retry_and_leaves_retries_at_zero() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": EchoLLMGateway()}, backoff_policy=_policy()
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.usage.retries == 0


@pytest.mark.asyncio
async def test_retries_the_same_candidate_and_records_the_retry_count() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    gateway = _FailNTimesGateway(fail_count=2, error=LLMProviderError("transient"))
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": gateway}, backoff_policy=_policy(max_attempts=3)
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert gateway.call_count == 3
    assert response.usage.retries == 2


@pytest.mark.asyncio
async def test_exhausting_all_retries_of_the_primary_falls_back() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    gateway_a = _FailNTimesGateway(fail_count=99, error=LLMProviderError("still down"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": gateway_a, "provider-b": EchoLLMGateway()},
        backoff_policy=_policy(max_attempts=3),
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert gateway_a.call_count == 3  # max_attempts exhausted before falling back
    assert response.usage.fallback_used is True


@pytest.mark.asyncio
async def test_raises_the_final_attempts_error_unchanged_when_no_fallback_is_configured() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    final_error = LLMProviderError("still down")
    gateway = _FailNTimesGateway(fail_count=99, error=final_error)
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": gateway}, backoff_policy=_policy(max_attempts=2)
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap"))

    assert gateway.call_count == 2
    assert exc_info.value is final_error


@pytest.mark.asyncio
async def test_backoff_stops_retrying_once_the_circuit_opens() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    gateway_a = _FailNTimesGateway(fail_count=99, error=LLMProviderError("down"))
    breaker = InMemoryCircuitBreaker(failure_threshold=1, reset_timeout_seconds=30.0)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": gateway_a, "provider-b": EchoLLMGateway()},
        circuit_breaker=breaker,
        backoff_policy=_policy(max_attempts=5),
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    # failure_threshold=1 means the very first failure already opens
    # the circuit — the retry loop must not attempt provider-a again.
    assert gateway_a.call_count == 1
    assert response.usage.fallback_used is True


@pytest.mark.asyncio
async def test_backoff_stops_retrying_once_the_total_time_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )

    class _SlowFailingGateway:
        def __init__(self) -> None:
            self.call_count = 0

        async def complete(self, request: LLMRequest) -> LLMResponse:
            self.call_count += 1
            clock[0] += 100.0  # simulate a slow failing call
            raise LLMProviderError("down")

    gateway = _SlowFailingGateway()
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": gateway},
        backoff_policy=_policy(max_attempts=10, max_total_seconds=5.0),
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    # The first call alone already consumed far more than the 5s budget.
    assert gateway.call_count == 1


# --- Retry & Fallback Manager: Error Taxonomy integration ---------------


@pytest.mark.asyncio
async def test_a_non_retriable_failure_is_never_retried_but_still_falls_back() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    gateway_a = _FailNTimesGateway(
        fail_count=99,
        error=LLMProviderError(
            "invalid request", category=ErrorCategory.PERMANENT, retriable=False
        ),
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": gateway_a, "provider-b": EchoLLMGateway()},
        backoff_policy=_policy(max_attempts=5),
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    # Not retried at all, despite max_attempts=5 — abandoned after the
    # first, non-retriable failure — but the chain still falls back.
    assert gateway_a.call_count == 1
    assert response.usage.fallback_used is True


@pytest.mark.asyncio
async def test_a_non_retriable_failure_with_no_fallback_raises_immediately() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    original_error = LLMProviderError(
        "invalid request", category=ErrorCategory.PERMANENT, retriable=False
    )
    gateway = _FailNTimesGateway(fail_count=99, error=original_error)
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": gateway}, backoff_policy=_policy(max_attempts=5)
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap"))

    assert gateway.call_count == 1
    assert exc_info.value is original_error


@pytest.mark.asyncio
async def test_backoff_honours_a_provider_supplied_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def _recording_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    gateway = _FailNTimesGateway(
        fail_count=1,
        error=LLMProviderError(
            "rate limited",
            category=ErrorCategory.TRANSIENT,
            retriable=True,
            retry_after_seconds=100.0,
        ),
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": gateway},
        backoff_policy=_policy(max_attempts=2, max_total_seconds=1000.0),
    )

    await dispatcher.complete(_request("fast-cheap"))

    # The provider's own hint (100s) must win over the policy's own,
    # much smaller computed jitter delay (base_delay_seconds=0.1,
    # capped at max_delay_seconds=1.0 in _policy()'s own defaults).
    assert delays == [100.0]


@pytest.mark.asyncio
async def test_the_circuit_breaker_does_not_count_a_permanent_failure() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    breaker = _RecordingCircuitBreaker()
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(
                LLMProviderError(
                    "invalid request", category=ErrorCategory.PERMANENT, retriable=False
                )
            )
        },
        circuit_breaker=breaker,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    assert breaker.calls == ["is_available:provider-a"]  # no "failure:provider-a" recorded


@pytest.mark.asyncio
async def test_the_circuit_breaker_does_count_an_infrastructure_failure() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    breaker = _RecordingCircuitBreaker()
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": _FailingGateway(
                LLMProviderError(
                    "auth failed", category=ErrorCategory.INFRASTRUCTURE, retriable=False
                )
            )
        },
        circuit_breaker=breaker,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    assert breaker.calls == ["is_available:provider-a", "failure:provider-a"]


@pytest.mark.asyncio
async def test_the_circuit_breaker_still_counts_an_unclassified_default_failure() -> None:
    # This step's own "preserve existing behaviour where no explicit
    # classification applies" requirement: a bare LLMProviderError
    # (defaulting to ErrorCategory.TRANSIENT) still counts, exactly as
    # every LLMProviderError did before the Error Taxonomy existed.
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    breaker = _RecordingCircuitBreaker()
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _FailingGateway(LLMProviderError("plain old failure"))},
        circuit_breaker=breaker,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    assert breaker.calls == ["is_available:provider-a", "failure:provider-a"]


# --- Policy & Budget Enforcer: first real slice -------------------------


class _CostlyGateway:
    """A real ``EchoLLMGateway`` response with ``usage.cost_usd``
    overridden to a chosen value — lets a test control exactly how much
    one call "spends" without needing a real provider."""

    def __init__(self, cost_usd: Decimal) -> None:
        self._cost_usd = cost_usd

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await EchoLLMGateway().complete(request)
        return response.model_copy(
            update={"usage": response.usage.model_copy(update={"cost_usd": self._cost_usd})}
        )


@pytest.mark.asyncio
async def test_no_budget_enforcer_configured_never_blocks_a_call() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _CostlyGateway(Decimal("1000.00"))}
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"


@pytest.mark.asyncio
async def test_a_within_budget_call_succeeds_and_records_its_spend() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        budget_enforcer=enforcer,
    )

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"
    assert enforcer.is_within_budget("fast-cheap") is True


@pytest.mark.asyncio
async def test_a_call_that_pushes_spend_over_the_ceiling_blocks_the_next_one() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("15.00"))},
        budget_enforcer=enforcer,
    )

    # The first call is itself allowed (the ceiling is checked using
    # spend recorded *before* this call, which starts at zero) — but it
    # pushes cumulative spend past the ceiling.
    await dispatcher.complete(_request("fast-cheap"))

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap"))

    assert exc_info.value.category == ErrorCategory.BUDGET
    assert exc_info.value.error_code == "llm.budget_exceeded"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_a_budget_exceeded_failure_never_falls_back() -> None:
    # The specific capability this step adds: unlike every other
    # category, a budget failure is scoped to the alias, not to any one
    # provider, so falling back to a different candidate can never be
    # the fix — the dispatcher must raise immediately, not exhaust the
    # chain first.
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    enforcer.record_spend("fast-cheap", Decimal("5.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _UnreachableGateway(), "provider-b": _UnreachableGateway()},
        budget_enforcer=enforcer,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap"))

    assert exc_info.value.category == ErrorCategory.BUDGET


@pytest.mark.asyncio
async def test_a_budget_exceeded_failure_is_never_retried_by_backoff() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    enforcer.record_spend("fast-cheap", Decimal("5.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _UnreachableGateway()},
        budget_enforcer=enforcer,
        backoff_policy=_policy(max_attempts=5),
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    # _UnreachableGateway raises AssertionError if ever called — the
    # test reaching this point at all already proves no attempt (real
    # or retried) was ever made against it.


@pytest.mark.asyncio
async def test_budgets_are_tracked_independently_per_alias() -> None:
    router = StaticRouter(
        routes={
            "fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a"),
            "reasoning": RoutingDecision(provider="provider-a", model_id="model-b"),
        }
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    enforcer.record_spend("fast-cheap", Decimal("20.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        budget_enforcer=enforcer,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap"))

    response = await dispatcher.complete(_request("reasoning"))
    assert response.content == "hello"


# --- Policy & Budget Enforcer: per-workflow ceiling ----------------------


@pytest.mark.asyncio
async def test_a_request_with_no_metadata_is_unaffected_by_a_workflow_budget_enforcer() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1000.00"))},
        workflow_budget_enforcer=enforcer,
    )

    # No workflow_id on this request's metadata (indeed no metadata at
    # all) — a configured workflow_budget_enforcer simply cannot check
    # it, so the call proceeds exactly as if no enforcer were configured.
    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"


@pytest.mark.asyncio
async def test_a_within_budget_workflow_call_succeeds_and_records_its_spend() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        workflow_budget_enforcer=enforcer,
    )

    response = await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    assert response.content == "hello"
    assert enforcer.is_within_budget("workflow-1") is True


@pytest.mark.asyncio
async def test_a_workflow_call_that_pushes_spend_over_the_ceiling_blocks_the_next_one() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("15.00"))},
        workflow_budget_enforcer=enforcer,
    )

    await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    assert exc_info.value.category == ErrorCategory.BUDGET
    assert exc_info.value.error_code == "llm.budget_exceeded"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_a_workflow_budget_exceeded_failure_never_falls_back() -> None:
    decision = build_routing_chain([("provider-a", "model-a"), ("provider-b", "model-b")])
    router = StaticRouter(routes={"fast-cheap": decision})
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    enforcer.record_spend("workflow-1", Decimal("5.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _UnreachableGateway(), "provider-b": _UnreachableGateway()},
        workflow_budget_enforcer=enforcer,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    assert exc_info.value.category == ErrorCategory.BUDGET


@pytest.mark.asyncio
async def test_a_workflow_budget_exceeded_failure_is_never_retried_by_backoff() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    enforcer.record_spend("workflow-1", Decimal("5.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _UnreachableGateway()},
        workflow_budget_enforcer=enforcer,
        backoff_policy=_policy(max_attempts=5),
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    # _UnreachableGateway raises AssertionError if ever called — the
    # test reaching this point at all already proves no attempt (real
    # or retried) was ever made against it.


@pytest.mark.asyncio
async def test_workflow_budgets_are_tracked_independently_per_workflow() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))
    enforcer.record_spend("workflow-1", Decimal("20.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        workflow_budget_enforcer=enforcer,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    response = await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-2"))
    assert response.content == "hello"


@pytest.mark.asyncio
async def test_alias_and_workflow_budget_enforcers_operate_independently() -> None:
    # Within the alias ceiling but over the workflow ceiling still fails...
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    alias_enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1000.00"))
    workflow_enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    workflow_enforcer.record_spend("workflow-1", Decimal("5.00"))
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        budget_enforcer=alias_enforcer,
        workflow_budget_enforcer=workflow_enforcer,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))
    assert exc_info.value.category == ErrorCategory.BUDGET

    # ...and, symmetrically, within the workflow ceiling but over the
    # alias ceiling also still fails.
    alias_enforcer_2 = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))
    alias_enforcer_2.record_spend("fast-cheap", Decimal("5.00"))
    workflow_enforcer_2 = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1000.00"))
    dispatcher_2 = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _CostlyGateway(Decimal("1.00"))},
        budget_enforcer=alias_enforcer_2,
        workflow_budget_enforcer=workflow_enforcer_2,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher_2.complete(_request("fast-cheap", workflow_id="workflow-2"))
    assert exc_info.value.category == ErrorCategory.BUDGET


# --- Policy & Budget Enforcer: per-step token/wall-time ceilings --------
# (`P02-S02-M06-T07`, 2026-08-10)


class _TokenHeavyGateway:
    """A real ``EchoLLMGateway`` response with ``usage.input_tokens``/
    ``output_tokens`` overridden — lets a test control exactly how many
    tokens one call "consumes" without needing a real provider."""

    def __init__(self, total_tokens: int) -> None:
        self._total_tokens = total_tokens

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await EchoLLMGateway().complete(request)
        return response.model_copy(
            update={
                "usage": response.usage.model_copy(
                    update={"input_tokens": self._total_tokens, "output_tokens": 0}
                )
            }
        )


class _SlowGateway:
    """A real ``EchoLLMGateway`` response with ``usage.latency_ms``
    overridden — lets a test control exactly how much wall-time one
    call "took" without a real, slow provider call."""

    def __init__(self, latency_ms: int) -> None:
        self._latency_ms = latency_ms

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await EchoLLMGateway().complete(request)
        return response.model_copy(
            update={"usage": response.usage.model_copy(update={"latency_ms": self._latency_ms})}
        )


@pytest.mark.asyncio
async def test_a_request_with_no_step_id_is_unaffected_by_a_step_token_budget_enforcer() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=1)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _TokenHeavyGateway(1_000_000)},
        step_token_budget_enforcer=enforcer,
    )

    # workflow_id present but no step_id — still nothing to key the
    # per-step ceiling by, so the call proceeds unaffected, the identical
    # "cannot be checked" shape the per-workflow ceiling already has.
    response = await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1"))

    assert response.content == "hello"


@pytest.mark.asyncio
async def test_a_within_budget_step_token_call_succeeds_and_records_its_usage() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=1000)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _TokenHeavyGateway(100)},
        step_token_budget_enforcer=enforcer,
    )

    response = await dispatcher.complete(
        _request("fast-cheap", workflow_id="workflow-1", step_id="build")
    )

    assert response.content == "hello"
    assert enforcer.is_within_budget("workflow-1:build") is True


@pytest.mark.asyncio
async def test_a_step_token_call_that_pushes_usage_over_the_ceiling_blocks_the_next_one() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=100)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _TokenHeavyGateway(150)},
        step_token_budget_enforcer=enforcer,
    )

    await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))

    assert exc_info.value.category == ErrorCategory.BUDGET
    assert exc_info.value.error_code == "llm.budget_exceeded"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_step_token_budgets_keep_the_same_step_id_apart_across_workflows() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=100)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _TokenHeavyGateway(150)},
        step_token_budget_enforcer=enforcer,
    )

    with pytest.raises(LLMProviderError):
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))

    # A different workflow's own "build" step is a genuinely separate
    # scope — the real reason this ceiling is keyed by (workflow_id,
    # step_id), never bare step_id.
    response = await dispatcher.complete(
        _request("fast-cheap", workflow_id="workflow-2", step_id="build")
    )
    assert response.content == "hello"


@pytest.mark.asyncio
async def test_a_within_budget_step_wall_time_call_succeeds_and_records_its_usage() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=10_000)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _SlowGateway(1_000)},
        step_wall_time_budget_enforcer=enforcer,
    )

    response = await dispatcher.complete(
        _request("fast-cheap", workflow_id="workflow-1", step_id="build")
    )

    assert response.content == "hello"
    assert enforcer.is_within_budget("workflow-1:build") is True


@pytest.mark.asyncio
async def test_a_step_wall_time_call_that_pushes_usage_over_the_ceiling_blocks_the_next_one() -> (
    None
):
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    enforcer = PerScopeCountBudgetEnforcer(ceiling=1_000)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _SlowGateway(1_500)},
        step_wall_time_budget_enforcer=enforcer,
    )

    await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))

    assert exc_info.value.category == ErrorCategory.BUDGET
    assert exc_info.value.error_code == "llm.budget_exceeded"


@pytest.mark.asyncio
async def test_step_token_and_step_wall_time_enforcers_operate_independently() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )

    class _TokenHeavyAndSlowGateway:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            response = await EchoLLMGateway().complete(request)
            return response.model_copy(
                update={
                    "usage": response.usage.model_copy(
                        update={"input_tokens": 5, "output_tokens": 0, "latency_ms": 1}
                    )
                }
            )

    # Over the token ceiling but within the wall-time ceiling still fails.
    token_enforcer = PerScopeCountBudgetEnforcer(ceiling=1)
    wall_time_enforcer = PerScopeCountBudgetEnforcer(ceiling=1_000_000)
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": _TokenHeavyAndSlowGateway()},
        step_token_budget_enforcer=token_enforcer,
        step_wall_time_budget_enforcer=wall_time_enforcer,
    )
    token_enforcer.record_usage("workflow-1:build", 5)

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.complete(_request("fast-cheap", workflow_id="workflow-1", step_id="build"))
    assert exc_info.value.category == ErrorCategory.BUDGET


# --- Capability Negotiator: matrix lookup ---------------------------------


def _capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        supports_tools=True,
        supports_parallel_tool_calls=True,
        supports_strict_tools=False,
        supports_structured_output=False,
        supports_streaming=True,
        supports_thinking=True,
        supports_effort=True,
        supports_prompt_caching=True,
        prompt_cache_min_tokens=1024,
        supports_vision=True,
        max_input_tokens=1_000_000,
        max_output_tokens=8192,
        accepts_sampling_params=False,
    )


def test_no_capability_negotiator_configured_raises_clearly() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError, match="no CapabilityNegotiator configured") as exc_info:
        dispatcher.capabilities("fast-cheap")

    assert exc_info.value.error_code == "llm.no_capability_negotiator"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_a_configured_negotiator_answers_capabilities_without_affecting_complete() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    capabilities = _capabilities()
    negotiator = StaticCapabilityNegotiator(
        router=router, capabilities_by_model_id={"model-a": capabilities}
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": EchoLLMGateway()},
        capability_negotiator=negotiator,
    )

    result = dispatcher.capabilities("fast-cheap")
    response = await dispatcher.complete(_request("fast-cheap"))

    assert result is capabilities
    assert response.content == "hello"


def test_capabilities_is_a_synchronous_method_not_a_coroutine() -> None:
    # platform_sdk.md §5.1's own documented signature is `def
    # capabilities(alias: str) -> ProviderCapabilities`, not `async def`
    # — unlike complete()/stream()/embed()/count_tokens(), answering it
    # needs no I/O.
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    negotiator = StaticCapabilityNegotiator(
        router=router, capabilities_by_model_id={"model-a": _capabilities()}
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"provider-a": EchoLLMGateway()},
        capability_negotiator=negotiator,
    )

    result = dispatcher.capabilities("fast-cheap")

    assert not asyncio.iscoroutine(result)
    assert isinstance(result, ProviderCapabilities)


@pytest.mark.asyncio
async def test_no_rate_limiter_configured_never_blocks_a_call() -> None:
    # P02-S02-M06-T11: the identical "absent means disabled, zero
    # observable change" default every other optional collaborator in
    # this class already establishes. The real, Redis-backed
    # RateLimiter itself, and its genuine over-limit-refusal behavior,
    # is proven against real Redis in
    # tests/integration/llm_gateway/test_rate_limiter.py — this is
    # pure-logic coverage of the default-off branch, needing no I/O.
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    response = await dispatcher.complete(_request("fast-cheap"))

    assert response.content == "hello"


# --- DispatchingLLMGateway.count_tokens() (P02-S02-M06-T10) ---------------


class _FakeTokenCountingGateway:
    """A real, deterministic fake implementing both ``LLMGateway`` and
    ``TokenCounter`` — used only to prove genuine resolution/dispatch
    wiring at this class's own level. The real provider-endpoint call
    itself (the actual token count) is proven against a real local HTTP
    server and, opt-in, the real live Anthropic API in
    tests/unit/kernel/llm_gateway/adapters/test_anthropic_adapter.py
    and tests/integration/llm_gateway/test_anthropic_adapter_live.py —
    this fake never claims to be that proof."""

    def __init__(self, count: int) -> None:
        self._count = count

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await EchoLLMGateway().complete(request)

    async def count_tokens(self, request: LLMRequest) -> int:
        return self._count


@pytest.mark.asyncio
async def test_count_tokens_resolves_the_alias_and_delegates_to_the_registered_gateway() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeTokenCountingGateway(42)}
    )

    count = await dispatcher.count_tokens(_request("fast-cheap"))

    assert count == 42


@pytest.mark.asyncio
async def test_count_tokens_raises_clearly_when_the_resolved_gateway_cannot_count() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.count_tokens(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_count_tokens_raises_clearly_for_an_unregistered_provider() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="unregistered-provider", model_id="x")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeTokenCountingGateway(42)}
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.count_tokens(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"


@pytest.mark.asyncio
async def test_count_tokens_never_falls_back_to_a_different_provider() -> None:
    # A token count is specific to the primary resolved model's own
    # tokenizer — a fallback candidate that *can* count must never be
    # silently substituted for a primary that cannot.
    router = StaticRouter(
        routes={
            "fast-cheap": RoutingDecision(
                provider="provider-a",
                model_id="model-a",
                fallback=RoutingDecision(provider="provider-b", model_id="model-b"),
            )
        }
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": EchoLLMGateway(),
            "provider-b": _FakeTokenCountingGateway(42),
        },
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.count_tokens(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"


# --- DispatchingLLMGateway.embed() (P02-S02-M06-T09) ----------------------


def _embedding_request(model_alias: str = "embedding-fast") -> EmbeddingRequest:
    return EmbeddingRequest(model_alias=model_alias, inputs=["hello"])


def _embedding_response(vector: list[float]) -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=[vector],
        model_id="model-a",
        model_version="model-a",
        dimensions=len(vector),
        usage=UsageRecord(
            input_tokens=1,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=1,
            provider="provider-a",
            model_id="model-a",
            retries=0,
            fallback_used=False,
        ),
    )


class _FakeEmbeddingGateway:
    """A real, deterministic fake implementing both ``LLMGateway`` and
    ``Embedder`` — used only to prove genuine resolution/dispatch
    wiring at this class's own level. The real provider-endpoint call
    itself is proven against a real local HTTP server in
    tests/unit/kernel/llm_gateway/adapters/test_local_adapter.py."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await EchoLLMGateway().complete(request)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return _embedding_response(self._vector)


@pytest.mark.asyncio
async def test_embed_resolves_the_alias_and_delegates_to_the_registered_gateway() -> None:
    router = StaticRouter(
        routes={"embedding-fast": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeEmbeddingGateway([0.1, 0.2])}
    )

    response = await dispatcher.embed(_embedding_request())

    assert response.vectors == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_embed_raises_clearly_when_the_resolved_gateway_cannot_embed() -> None:
    router = StaticRouter(
        routes={"embedding-fast": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.embed(_embedding_request())

    assert exc_info.value.error_code == "llm.capability_unsupported"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_embed_raises_clearly_for_an_unregistered_provider() -> None:
    router = StaticRouter(
        routes={"embedding-fast": RoutingDecision(provider="unregistered-provider", model_id="x")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeEmbeddingGateway([0.1])}
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.embed(_embedding_request())

    assert exc_info.value.error_code == "llm.capability_unsupported"


@pytest.mark.asyncio
async def test_embed_never_falls_back_to_a_different_provider() -> None:
    # An embedding is specific to the primary resolved model's own
    # vector space -- a fallback candidate that *can* embed must never
    # be silently substituted for a primary that cannot.
    router = StaticRouter(
        routes={
            "embedding-fast": RoutingDecision(
                provider="provider-a",
                model_id="model-a",
                fallback=RoutingDecision(provider="provider-b", model_id="model-b"),
            )
        }
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": EchoLLMGateway(),
            "provider-b": _FakeEmbeddingGateway([0.1]),
        },
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await dispatcher.embed(_embedding_request())

    assert exc_info.value.error_code == "llm.capability_unsupported"


# --- DispatchingLLMGateway.stream() (P02-S02-M06-T08) ---------------------


class _FakeStreamingGateway:
    """A real, deterministic fake implementing both ``LLMGateway`` and
    ``Streamer`` -- used only to prove genuine resolution/dispatch
    wiring at this class's own level. The real provider-endpoint
    streaming call itself is proven against a real local SSE server in
    tests/unit/kernel/llm_gateway/adapters/test_anthropic_adapter.py."""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await EchoLLMGateway().complete(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        for delta in self._deltas:
            yield LLMStreamEvent(type=StreamEventType.CONTENT_DELTA, delta=delta)


@pytest.mark.asyncio
async def test_stream_resolves_the_alias_and_delegates_to_the_registered_gateway() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeStreamingGateway(["a", "b"])}
    )

    events = [event async for event in dispatcher.stream(_request("fast-cheap"))]

    assert [event.delta for event in events] == ["a", "b"]


@pytest.mark.asyncio
async def test_stream_raises_clearly_when_the_resolved_gateway_cannot_stream() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="provider-a", model_id="model-a")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={"provider-a": EchoLLMGateway()})

    with pytest.raises(LLMProviderError) as exc_info:
        dispatcher.stream(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_stream_raises_clearly_for_an_unregistered_provider() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="unregistered-provider", model_id="x")}
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={"provider-a": _FakeStreamingGateway(["a"])}
    )

    with pytest.raises(LLMProviderError) as exc_info:
        dispatcher.stream(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"


@pytest.mark.asyncio
async def test_stream_raises_eagerly_before_any_iteration_not_lazily_on_first_next() -> None:
    # DispatchingLLMGateway.stream() is deliberately not `async def` --
    # resolution/capability-check errors must surface at call time,
    # not only once a caller starts iterating.
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="unregistered-provider", model_id="x")}
    )
    dispatcher = DispatchingLLMGateway(router=router, gateways={})

    raised_at_call_time = False
    try:
        dispatcher.stream(_request("fast-cheap"))
    except LLMProviderError:
        raised_at_call_time = True

    assert raised_at_call_time


@pytest.mark.asyncio
async def test_stream_never_falls_back_to_a_different_provider() -> None:
    # A stream that has already delivered real partial content to the
    # caller must never silently restart against a different fallback
    # candidate.
    router = StaticRouter(
        routes={
            "fast-cheap": RoutingDecision(
                provider="provider-a",
                model_id="model-a",
                fallback=RoutingDecision(provider="provider-b", model_id="model-b"),
            )
        }
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={
            "provider-a": EchoLLMGateway(),
            "provider-b": _FakeStreamingGateway(["a"]),
        },
    )

    with pytest.raises(LLMProviderError) as exc_info:
        dispatcher.stream(_request("fast-cheap"))

    assert exc_info.value.error_code == "llm.capability_unsupported"
