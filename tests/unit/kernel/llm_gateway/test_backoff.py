"""Unit tests for the Retry & Fallback Manager's backoff policy
(ai_os_kernel.llm_gateway.backoff.BackoffPolicy): pure computation, no
real sleeping, no real randomness left uncontrolled where the test
needs a deterministic answer.
"""

import random

import pytest

from ai_os_kernel.llm_gateway.backoff import BackoffPolicy


def test_delay_seconds_is_bounded_by_the_exponential_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin random.uniform to always return its upper bound, so the delay
    # is deterministic and equals the exponential cap exactly.
    monkeypatch.setattr(random, "uniform", lambda low, high: high)
    policy = BackoffPolicy(
        max_attempts=5,
        base_delay_seconds=1.0,
        max_delay_seconds=100.0,
        max_total_seconds=1000.0,
    )

    assert policy.delay_seconds(1) == 1.0
    assert policy.delay_seconds(2) == 2.0
    assert policy.delay_seconds(3) == 4.0
    assert policy.delay_seconds(4) == 8.0


def test_delay_seconds_is_capped_at_max_delay_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "uniform", lambda low, high: high)
    policy = BackoffPolicy(
        max_attempts=10,
        base_delay_seconds=1.0,
        max_delay_seconds=5.0,
        max_total_seconds=1000.0,
    )

    # Uncapped this would be 1 * 2**9 = 512; the cap must win.
    assert policy.delay_seconds(10) == 5.0


def test_delay_seconds_draws_from_a_uniform_distribution_between_zero_and_the_cap() -> None:
    policy = BackoffPolicy(
        max_attempts=5,
        base_delay_seconds=1.0,
        max_delay_seconds=100.0,
        max_total_seconds=1000.0,
    )

    delay = policy.delay_seconds(1)

    assert 0.0 <= delay <= 1.0


def test_rejects_a_max_attempts_below_one() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        BackoffPolicy(
            max_attempts=0,
            base_delay_seconds=1.0,
            max_delay_seconds=10.0,
            max_total_seconds=30.0,
        )


@pytest.mark.parametrize(
    "field",
    ["base_delay_seconds", "max_delay_seconds", "max_total_seconds"],
)
def test_rejects_a_non_positive_duration(field: str) -> None:
    kwargs = {
        "max_attempts": 3,
        "base_delay_seconds": 1.0,
        "max_delay_seconds": 10.0,
        "max_total_seconds": 30.0,
    }
    kwargs[field] = 0.0

    with pytest.raises(ValueError, match="must be positive"):
        BackoffPolicy(**kwargs)
