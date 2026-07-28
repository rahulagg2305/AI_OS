"""Unit tests for the Capability Negotiator's matrix lookup
(ai_os_kernel.llm_gateway.capability_negotiator): the ``ProviderCapabilities``
model's own validation, and ``StaticCapabilityNegotiator``'s alias ->
model id -> matrix resolution — no network, no I/O."""

import pytest
from pydantic import ValidationError

from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities,
    StaticCapabilityNegotiator,
)
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter


def _capabilities(**overrides: object) -> ProviderCapabilities:
    fields: dict[str, object] = {
        "supports_tools": True,
        "supports_parallel_tool_calls": True,
        "supports_strict_tools": False,
        "supports_structured_output": False,
        "supports_streaming": True,
        "supports_thinking": True,
        "supports_effort": True,
        "supports_prompt_caching": True,
        "prompt_cache_min_tokens": 1024,
        "supports_vision": True,
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 8192,
        "accepts_sampling_params": False,
    }
    fields.update(overrides)
    return ProviderCapabilities(**fields)


# --- ProviderCapabilities model validation --------------------------------


def test_a_well_formed_capabilities_matrix_is_accepted() -> None:
    capabilities = _capabilities()

    assert capabilities.supports_tools is True
    assert capabilities.max_input_tokens == 1_000_000


def test_capabilities_is_frozen() -> None:
    capabilities = _capabilities()

    with pytest.raises(ValidationError):
        capabilities.supports_tools = False  # type: ignore[misc]


def test_prompt_cache_min_tokens_may_be_none_when_caching_is_unsupported() -> None:
    capabilities = _capabilities(supports_prompt_caching=False, prompt_cache_min_tokens=None)

    assert capabilities.prompt_cache_min_tokens is None


def test_rejects_a_prompt_cache_minimum_when_caching_is_unsupported() -> None:
    with pytest.raises(ValidationError, match="must be omitted"):
        _capabilities(supports_prompt_caching=False, prompt_cache_min_tokens=1024)


def test_rejects_missing_prompt_cache_minimum_when_caching_is_supported() -> None:
    with pytest.raises(ValidationError, match="must be set"):
        _capabilities(supports_prompt_caching=True, prompt_cache_min_tokens=None)


@pytest.mark.parametrize("field", ["max_input_tokens", "max_output_tokens"])
def test_rejects_a_non_positive_token_ceiling(field: str) -> None:
    with pytest.raises(ValidationError, match="must both be positive"):
        _capabilities(**{field: 0})


# --- StaticCapabilityNegotiator --------------------------------------------


def _negotiator(
    routes: dict[str, RoutingDecision], capabilities_by_model_id: dict[str, ProviderCapabilities]
) -> StaticCapabilityNegotiator:
    return StaticCapabilityNegotiator(
        router=StaticRouter(routes=routes),
        capabilities_by_model_id=capabilities_by_model_id,
    )


def test_resolves_the_alias_to_its_model_ids_capabilities() -> None:
    capabilities = _capabilities()
    negotiator = _negotiator(
        routes={
            "coding-balanced": RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")
        },
        capabilities_by_model_id={"claude-sonnet-5": capabilities},
    )

    result = negotiator.capabilities("coding-balanced")

    assert result is capabilities


def test_two_aliases_resolving_to_the_same_model_id_get_the_same_capabilities() -> None:
    capabilities = _capabilities()
    negotiator = _negotiator(
        routes={
            "reasoning": RoutingDecision(provider="anthropic", model_id="claude-opus-5"),
            "coding-strong": RoutingDecision(provider="anthropic", model_id="claude-opus-5"),
        },
        capabilities_by_model_id={"claude-opus-5": capabilities},
    )

    assert negotiator.capabilities("reasoning") is capabilities
    assert negotiator.capabilities("coding-strong") is capabilities


def test_raises_clearly_for_an_alias_the_router_does_not_know() -> None:
    negotiator = _negotiator(routes={}, capabilities_by_model_id={})

    with pytest.raises(LLMProviderError, match="no configured route"):
        negotiator.capabilities("does-not-exist")


def test_raises_clearly_when_the_resolved_model_id_has_no_capabilities_entry() -> None:
    negotiator = _negotiator(
        routes={
            "coding-balanced": RoutingDecision(provider="anthropic", model_id="claude-sonnet-5")
        },
        capabilities_by_model_id={},
    )

    with pytest.raises(LLMProviderError, match="no configured capability matrix entry") as exc_info:
        negotiator.capabilities("coding-balanced")

    assert exc_info.value.error_code == "llm.no_capabilities"
    assert exc_info.value.retriable is False
