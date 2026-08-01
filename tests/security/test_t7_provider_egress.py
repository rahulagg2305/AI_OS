"""T7 — Data exfiltration to a model provider (security_architecture.md
§4/§11). Real defense exercised here: the provider allowlist "by
construction" — llm_gateway.md's Router only ever resolves an alias to a
provider someone explicitly configured (ADR-0002: callers never name a
literal model id or provider). An unconfigured/arbitrary alias has
nothing to route to.

The attempt: a caller (or a compromised component further up the chain)
supplies an alias never configured by an operator — e.g. one naming an
arbitrary, unapproved destination directly — and the real
:class:`~ai_os_kernel.llm_gateway.router.StaticRouter` must fail closed,
never silently routing anywhere.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.llm_gateway.error_taxonomy import NO_ROUTE
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter


def test_a_real_attempt_to_reach_an_unconfigured_provider_fails_closed() -> None:
    """Only `trusted-alias` was ever configured by an operator — a
    request for anything else (a compromised caller trying to reach an
    arbitrary destination) must be refused, never silently served."""
    router = StaticRouter(
        routes={"trusted-alias": RoutingDecision(provider="anthropic", model_id="claude-fast")}
    )

    with pytest.raises(LLMProviderError) as exc_info:
        router.resolve("attacker-supplied-arbitrary-destination")

    assert exc_info.value.category == NO_ROUTE.category
    assert exc_info.value.error_code == NO_ROUTE.error_code
    assert exc_info.value.retriable is False


def test_a_configured_alias_still_resolves_normally() -> None:
    """Proportionality check: the allowlist blocks only what was never
    configured — a real, operator-approved alias still resolves."""
    router = StaticRouter(
        routes={"trusted-alias": RoutingDecision(provider="anthropic", model_id="claude-fast")}
    )

    decision = router.resolve("trusted-alias")

    assert decision.provider == "anthropic"
    assert decision.model_id == "claude-fast"
