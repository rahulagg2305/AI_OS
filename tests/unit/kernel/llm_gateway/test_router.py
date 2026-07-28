"""Unit tests for the Router (ai_os_kernel.llm_gateway.router): a
deterministic, configuration-driven ``model_alias -> RoutingDecision``
resolver, no network, no I/O.
"""

import pytest

from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter, build_routing_chain


def test_resolve_returns_the_configured_routing_decision() -> None:
    router = StaticRouter(
        routes={
            "coding-balanced": RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")
        }
    )

    decision = router.resolve("coding-balanced")

    assert decision == RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")


def test_resolve_raises_for_an_unconfigured_alias() -> None:
    router = StaticRouter(routes={})

    with pytest.raises(LLMProviderError, match="no configured route") as exc_info:
        router.resolve("does-not-exist")

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.no_route"
    assert exc_info.value.retriable is False


def test_resolve_is_deterministic_across_repeated_calls() -> None:
    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider="anthropic", model_id="claude-haiku-4-5")}
    )

    first = router.resolve("fast-cheap")
    second = router.resolve("fast-cheap")

    assert first == second


def test_the_router_does_not_share_state_with_the_mapping_passed_in() -> None:
    routes = {"fast-cheap": RoutingDecision(provider="anthropic", model_id="claude-haiku-4-5")}
    router = StaticRouter(routes=routes)
    routes["fast-cheap"] = RoutingDecision(
        provider="anthropic", model_id="mutated-after-construction"
    )

    decision = router.resolve("fast-cheap")

    assert decision.model_id == "claude-haiku-4-5"


def test_different_aliases_can_resolve_to_different_providers() -> None:
    # The specific capability this step adds: a single Router instance
    # genuinely routing different aliases to different providers, not
    # one default_provider applied to every alias.
    router = StaticRouter(
        routes={
            "coding-balanced": RoutingDecision(provider="anthropic", model_id="claude-sonnet-5"),
            "local-echo": RoutingDecision(provider="echo", model_id="echo-1"),
        }
    )

    assert router.resolve("coding-balanced").provider == "anthropic"
    assert router.resolve("local-echo").provider == "echo"


def test_a_routing_decision_has_no_fallback_by_default() -> None:
    decision = RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")

    assert decision.fallback is None


def test_a_routing_decision_can_carry_an_explicit_fallback() -> None:
    decision = RoutingDecision(
        provider="anthropic",
        model_id="claude-sonnet-5",
        fallback=RoutingDecision(provider="local", model_id="llama3.1:8b"),
    )

    assert decision.fallback == RoutingDecision(provider="local", model_id="llama3.1:8b")


def test_build_routing_chain_with_one_candidate_has_no_fallback() -> None:
    decision = build_routing_chain([("anthropic", "claude-sonnet-5")])

    assert decision == RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")
    assert decision.fallback is None


def test_build_routing_chain_links_candidates_in_order() -> None:
    decision = build_routing_chain(
        [
            ("anthropic", "claude-sonnet-5"),
            ("local", "llama3.1:8b"),
            ("anthropic", "claude-haiku-4-5"),
        ]
    )

    assert decision.provider == "anthropic"
    assert decision.model_id == "claude-sonnet-5"
    assert decision.fallback is not None
    assert decision.fallback.provider == "local"
    assert decision.fallback.model_id == "llama3.1:8b"
    assert decision.fallback.fallback is not None
    assert decision.fallback.fallback.provider == "anthropic"
    assert decision.fallback.fallback.model_id == "claude-haiku-4-5"
    assert decision.fallback.fallback.fallback is None


def test_build_routing_chain_raises_for_an_empty_sequence() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_routing_chain([])
