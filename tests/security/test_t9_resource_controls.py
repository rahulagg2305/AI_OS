"""T9 — Resource exhaustion (security_architecture.md §4/§13). Real
defense exercised here: the Policy & Budget Enforcer's real cost ceiling
(§13: "budgets in Gateway") — :class:`~ai_os_kernel.llm_gateway.
budget_enforcer.PerScopeBudgetEnforcer`, checked by
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` before
any provider is even consulted.

The attempt: a caller (or a runaway loop) keeps spending against one
alias past its configured ceiling — the real gateway must refuse the
next call outright, never attempting a provider, and the failure must
carry the real ``budget`` classification (not a generic error) so a
caller can distinguish "you are out of budget" from a transient
provider hiccup.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer
from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter


def test_a_real_ceiling_is_genuinely_exceeded_by_real_recorded_spend() -> None:
    """The enforcer's own ceiling check, against real accumulated spend
    (not a mocked comparison)."""
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))

    assert enforcer.is_within_budget("fast-cheap") is True

    enforcer.record_spend("fast-cheap", Decimal("0.60"))
    enforcer.record_spend("fast-cheap", Decimal("0.55"))

    assert enforcer.is_within_budget("fast-cheap") is False


@pytest.mark.asyncio
async def test_a_real_runaway_caller_is_refused_before_any_provider_is_ever_attempted() -> None:
    """End to end through the real dispatching gateway: an alias that
    has already exceeded its ceiling is refused outright — the
    `gateways` mapping below is deliberately empty, so a provider
    attempt reaching it at all would raise a different, unrelated
    error, proving the budget gate fires first."""
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("0.01"))
    enforcer.record_spend("runaway-alias", Decimal("5.00"))

    router = StaticRouter(
        routes={"runaway-alias": RoutingDecision(provider="anthropic", model_id="claude-fast")}
    )
    gateway = DispatchingLLMGateway(router=router, gateways={}, budget_enforcer=enforcer)
    request = LLMRequest(
        model_alias="runaway-alias",
        messages=[Message(role=MessageRole.USER, content="keep going")],
        max_output_tokens=256,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await gateway.complete(request)

    assert exc_info.value.category == ErrorCategory.BUDGET
    assert exc_info.value.error_code == "llm.budget_exceeded"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_a_fresh_scope_never_seen_before_is_not_falsely_throttled() -> None:
    """Proportionality check: the control gates real overspend, not
    every request — a scope with no recorded spend yet is within
    budget."""
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("1.00"))

    assert enforcer.is_within_budget("never-used-before") is True
