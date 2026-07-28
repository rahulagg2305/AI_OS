"""Unit tests for the Policy & Budget Enforcer's first real slice
(ai_os_kernel.llm_gateway.budget_enforcer): per-alias cumulative-spend
tracking, no network, no I/O.
"""

from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer


def _enforcer(ceiling_usd: str = "10.00") -> PerScopeBudgetEnforcer:
    return PerScopeBudgetEnforcer(ceiling_usd=Decimal(ceiling_usd))


def test_an_unseen_alias_is_within_budget() -> None:
    enforcer = _enforcer()

    assert enforcer.is_within_budget("fast-cheap") is True


def test_spend_below_the_ceiling_stays_within_budget() -> None:
    enforcer = _enforcer("10.00")

    enforcer.record_spend("fast-cheap", Decimal("5.00"))

    assert enforcer.is_within_budget("fast-cheap") is True


def test_spend_reaching_the_ceiling_is_no_longer_within_budget() -> None:
    enforcer = _enforcer("10.00")

    enforcer.record_spend("fast-cheap", Decimal("6.00"))
    enforcer.record_spend("fast-cheap", Decimal("4.00"))

    assert enforcer.is_within_budget("fast-cheap") is False


def test_spend_exceeding_the_ceiling_is_no_longer_within_budget() -> None:
    enforcer = _enforcer("10.00")

    enforcer.record_spend("fast-cheap", Decimal("15.00"))

    assert enforcer.is_within_budget("fast-cheap") is False


def test_spend_accumulates_across_multiple_records() -> None:
    enforcer = _enforcer("10.00")

    enforcer.record_spend("fast-cheap", Decimal("3.00"))
    enforcer.record_spend("fast-cheap", Decimal("3.00"))

    assert enforcer.is_within_budget("fast-cheap") is True

    enforcer.record_spend("fast-cheap", Decimal("3.00"))
    enforcer.record_spend("fast-cheap", Decimal("3.00"))

    assert enforcer.is_within_budget("fast-cheap") is False


def test_aliases_are_tracked_independently() -> None:
    enforcer = _enforcer("10.00")

    enforcer.record_spend("fast-cheap", Decimal("20.00"))

    assert enforcer.is_within_budget("fast-cheap") is False
    assert enforcer.is_within_budget("reasoning") is True


def test_rejects_a_non_positive_ceiling() -> None:
    with pytest.raises(ValueError, match="ceiling_usd"):
        PerScopeBudgetEnforcer(ceiling_usd=Decimal("0"))
