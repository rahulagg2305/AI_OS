"""Unit tests for the Policy & Budget Enforcer
(ai_os_kernel.llm_gateway.budget_enforcer): per-alias/per-workflow
cumulative-spend tracking, and the per-step token/wall-time count
tracking added `P02-S02-M06-T07` — no network, no I/O.
"""

from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.budget_enforcer import (
    PerScopeBudgetEnforcer,
    PerScopeCountBudgetEnforcer,
    step_scope,
)


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


def test_step_scope_builds_the_composite_key() -> None:
    assert step_scope("wf_1", "build") == "wf_1:build"


def test_step_scope_keeps_two_different_workflows_of_the_same_step_id_apart() -> None:
    assert step_scope("wf_1", "build") != step_scope("wf_2", "build")


def _count_enforcer(ceiling: int = 100) -> PerScopeCountBudgetEnforcer:
    return PerScopeCountBudgetEnforcer(ceiling=ceiling)


def test_an_unseen_count_scope_is_within_budget() -> None:
    enforcer = _count_enforcer()

    assert enforcer.is_within_budget(step_scope("wf_1", "build")) is True


def test_count_usage_below_the_ceiling_stays_within_budget() -> None:
    enforcer = _count_enforcer(100)
    scope = step_scope("wf_1", "build")

    enforcer.record_usage(scope, 50)

    assert enforcer.is_within_budget(scope) is True


def test_count_usage_reaching_the_ceiling_is_no_longer_within_budget() -> None:
    enforcer = _count_enforcer(100)
    scope = step_scope("wf_1", "build")

    enforcer.record_usage(scope, 60)
    enforcer.record_usage(scope, 40)

    assert enforcer.is_within_budget(scope) is False


def test_count_usage_accumulates_across_multiple_records() -> None:
    enforcer = _count_enforcer(100)
    scope = step_scope("wf_1", "build")

    enforcer.record_usage(scope, 30)
    enforcer.record_usage(scope, 30)

    assert enforcer.is_within_budget(scope) is True

    enforcer.record_usage(scope, 30)
    enforcer.record_usage(scope, 30)

    assert enforcer.is_within_budget(scope) is False


def test_count_scopes_are_tracked_independently() -> None:
    enforcer = _count_enforcer(100)

    enforcer.record_usage(step_scope("wf_1", "build"), 200)

    assert enforcer.is_within_budget(step_scope("wf_1", "build")) is False
    # A different workflow's own "build" step is a genuinely different
    # scope key — the real reason step ceilings must be keyed by the
    # composite (workflow_id, step_id), never bare step_id.
    assert enforcer.is_within_budget(step_scope("wf_2", "build")) is True


def test_count_enforcer_rejects_a_non_positive_ceiling() -> None:
    with pytest.raises(ValueError, match="ceiling"):
        PerScopeCountBudgetEnforcer(ceiling=0)
