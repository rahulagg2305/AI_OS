"""Opt-in, real-network verification of :class:`AnthropicAdapter` against
the actual Anthropic API — **not** part of the merge-path guarantee
(ADR-0015's "real, not mocked" convention is about local, free,
deterministic backends like Postgres; a paid, live external provider is
a different kind of dependency, so this suite is skipped by default
rather than required).

Skipped unless a real key is available at the documented local-dev
secret reference (``secret://env/llm/anthropic-api-key``, resolved by
``EnvSecretProvider`` to the ``AIOS_SECRET_LLM_ANTHROPIC_API_KEY``
environment variable — the exact example
``ai_os_kernel.secrets_manager.env_provider`` already uses in its own
docstring). See this step's own report for how to set this variable and
run this file directly to manually verify a real call.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole, StopReason
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider

REPO_ROOT = Path(__file__).resolve().parents[3]
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

pytestmark = pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)


@pytest.mark.asyncio
async def test_a_real_completion_against_the_live_anthropic_api() -> None:
    config = load_provider_config(REPO_ROOT / "config" / "llm.yaml")
    adapter = await build_anthropic_adapter(
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=StaticRouter(
            routes={
                alias: RoutingDecision(
                    provider=config.providers.get(alias, PROVIDER_NAME), model_id=model_id
                )
                for alias, model_id in config.model_ids.items()
            }
        ),
        pricing=config.pricing,
    )
    request = LLMRequest(
        model_alias="fast-cheap",
        messages=[Message(role=MessageRole.USER, content="Reply with exactly the word: pong")],
        max_output_tokens=16,
    )

    response = await adapter.complete(request)

    assert response.provider == "anthropic"
    assert response.model_id.startswith("claude-")
    assert response.stop_reason in (StopReason.END_TURN, StopReason.MAX_TOKENS)
    assert response.content.strip() != ""
    assert response.usage.cost_usd > Decimal("0")
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0


@pytest.mark.asyncio
async def test_a_real_token_count_against_the_live_anthropic_api() -> None:
    """llm_gateway.md §12, P02-S02-M06-T10: a genuine, exact count from
    Anthropic's own real ``/v1/messages/count_tokens`` endpoint — not a
    character-length heuristic. The unit suite
    (``tests/unit/kernel/llm_gateway/adapters/test_anthropic_adapter.py``)
    already proves the request/response wire format against a real
    local HTTP server; this is the one test in this tree that proves
    the real Anthropic service itself answers this real request the
    way this adapter assumes."""
    config = load_provider_config(REPO_ROOT / "config" / "llm.yaml")
    adapter = await build_anthropic_adapter(
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=StaticRouter(
            routes={
                alias: RoutingDecision(
                    provider=config.providers.get(alias, PROVIDER_NAME), model_id=model_id
                )
                for alias, model_id in config.model_ids.items()
            }
        ),
        pricing=config.pricing,
    )
    short_request = LLMRequest(
        model_alias="fast-cheap",
        messages=[Message(role=MessageRole.USER, content="hi")],
        max_output_tokens=16,
    )
    longer_request = LLMRequest(
        model_alias="fast-cheap",
        messages=[
            Message(
                role=MessageRole.USER,
                content="Please write several complete sentences about the ocean.",
            )
        ],
        max_output_tokens=16,
    )

    short_count = await adapter.count_tokens(short_request)
    longer_count = await adapter.count_tokens(longer_request)

    assert isinstance(short_count, int)
    assert short_count > 0
    # A genuinely longer prompt must produce a genuinely larger real
    # count -- the one property that would catch this silently
    # degrading into a fixed or heuristic stand-in.
    assert longer_count > short_count
