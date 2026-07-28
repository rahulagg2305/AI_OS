"""Unit tests for the Retry & Fallback Manager's Circuit Breaker
(ai_os_kernel.llm_gateway.circuit_breaker): per-provider, in-process,
three-state (CLOSED/OPEN/HALF_OPEN) failure memory. No real network, no
real time passing — the reset timer is exercised by monkeypatching
``time.monotonic`` deterministically rather than sleeping.
"""

import time

import pytest

from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker


def _breaker(
    *, failure_threshold: int = 3, reset_timeout_seconds: float = 10.0
) -> InMemoryCircuitBreaker:
    return InMemoryCircuitBreaker(
        failure_threshold=failure_threshold, reset_timeout_seconds=reset_timeout_seconds
    )


def test_an_unseen_provider_is_available() -> None:
    breaker = _breaker()

    assert breaker.is_available("anthropic") is True


def test_fewer_than_threshold_failures_keeps_the_circuit_available() -> None:
    breaker = _breaker(failure_threshold=3)

    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")

    assert breaker.is_available("anthropic") is True


def test_reaching_the_failure_threshold_opens_the_circuit() -> None:
    breaker = _breaker(failure_threshold=3)

    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")

    assert breaker.is_available("anthropic") is False


def test_a_success_resets_the_consecutive_failure_count() -> None:
    breaker = _breaker(failure_threshold=3)

    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")
    breaker.record_success("anthropic")
    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")

    # Four failures total, but the success reset the streak — only two
    # consecutive failures follow it, below the threshold of three.
    assert breaker.is_available("anthropic") is True


def test_circuits_are_tracked_independently_per_provider() -> None:
    breaker = _breaker(failure_threshold=1)

    breaker.record_failure("anthropic")

    assert breaker.is_available("anthropic") is False
    assert breaker.is_available("local") is True


def test_the_circuit_stays_open_until_the_reset_timeout_elapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    breaker = _breaker(failure_threshold=1, reset_timeout_seconds=10.0)

    breaker.record_failure("anthropic")
    assert breaker.is_available("anthropic") is False

    clock[0] = 5.0
    assert breaker.is_available("anthropic") is False

    clock[0] = 10.0
    assert breaker.is_available("anthropic") is True


def test_a_successful_half_open_trial_fully_closes_the_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    breaker = _breaker(failure_threshold=2, reset_timeout_seconds=10.0)

    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")
    clock[0] = 10.0
    assert breaker.is_available("anthropic") is True  # now half-open

    breaker.record_success("anthropic")

    # Fully closed, with a fresh failure count: one failure alone
    # (below the threshold of two) must not reopen it.
    breaker.record_failure("anthropic")
    assert breaker.is_available("anthropic") is True


def test_a_failed_half_open_trial_reopens_the_circuit_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    breaker = _breaker(failure_threshold=3, reset_timeout_seconds=10.0)

    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")
    breaker.record_failure("anthropic")
    clock[0] = 10.0
    assert breaker.is_available("anthropic") is True  # now half-open

    breaker.record_failure("anthropic")  # the trial call itself fails

    assert breaker.is_available("anthropic") is False
    clock[0] = 19.9
    assert breaker.is_available("anthropic") is False
    clock[0] = 20.0
    assert breaker.is_available("anthropic") is True


def test_rejects_a_failure_threshold_below_one() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        InMemoryCircuitBreaker(failure_threshold=0, reset_timeout_seconds=1.0)


def test_rejects_a_non_positive_reset_timeout() -> None:
    with pytest.raises(ValueError, match="reset_timeout_seconds"):
        InMemoryCircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.0)
