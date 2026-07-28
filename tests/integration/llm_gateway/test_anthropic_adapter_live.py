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
