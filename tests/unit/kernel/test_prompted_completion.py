"""Unit tests for PromptedCompletionService: composition logic only,
using InMemoryPromptEngine/EchoLLMGateway plus a fake recorder — no
real database, no real provider.

Also covers ``build_anthropic_prompted_completion_service``'s own
construction-time wiring (secret resolution + composing the three real
implementations) — still no real database and no real network, since
none of `AsyncEngine`/`SqlPromptCatalog`/`SqlLLMCallRecorder`/
`AnthropicAdapter` do any I/O until a method is actually awaited.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import PROVIDER_NAME, AnthropicAdapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer
from ai_os_kernel.llm_gateway.call_recorder import SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities,
    StaticCapabilityNegotiator,
)
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse, TraceContext
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import (
    PromptedCompletionService,
    build_anthropic_prompted_completion_service,
)
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider


class _FakeCallRecorder:
    """Records every call made to it; never touches a database."""

    def __init__(self) -> None:
        self.record_calls: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        request: LLMRequest,
        response: LLMResponse,
        workflow_id: str,
        step_id: str,
        agent_id: str | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        self.record_calls.append(
            {
                "request": request,
                "response": response,
                "workflow_id": workflow_id,
                "step_id": step_id,
                "agent_id": agent_id,
                "prompt_id": prompt_id,
                "prompt_version": prompt_version,
            }
        )


def _service(call_recorder: _FakeCallRecorder | None = None) -> PromptedCompletionService:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})
    return PromptedCompletionService(
        prompt_engine=engine,
        llm_gateway=EchoLLMGateway(),
        call_recorder=call_recorder,
    )


class _RequestCapturingGateway:
    """Delegates to a real ``EchoLLMGateway`` but also keeps the last
    ``LLMRequest`` it was given, so a test can inspect ``metadata``
    without needing a real provider."""

    def __init__(self) -> None:
        self.last_request: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return await EchoLLMGateway().complete(request)


@pytest.mark.asyncio
async def test_renders_the_prompt_and_completes_from_it() -> None:
    service = _service()

    result = await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
    )

    assert result.render.content == "Hello, Ada!"
    assert result.render.prompt_id == "prompt_greeting"
    assert result.render.version == "1.0.0"
    assert result.response.content == "Hello, Ada!"


@pytest.mark.asyncio
async def test_the_llm_request_carries_the_rendered_content_as_the_user_message() -> None:
    service = _service()

    result = await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=5,
    )

    # EchoLLMGateway echoes and truncates the last message to max_output_tokens.
    assert result.response.content == "Hello"


@pytest.mark.asyncio
async def test_no_variables_is_accepted_when_the_template_needs_none() -> None:
    engine = InMemoryPromptEngine({("prompt_static", "1.0.0"): "You are a helpful assistant."})
    service = PromptedCompletionService(prompt_engine=engine, llm_gateway=EchoLLMGateway())

    result = await service.complete_from_prompt(
        prompt_id="prompt_static",
        prompt_version="1.0.0",
        model_alias="fast-cheap",
        max_output_tokens=100,
    )

    assert result.render.content == "You are a helpful assistant."


@pytest.mark.asyncio
async def test_records_the_call_when_a_recorder_and_workflow_step_context_are_given() -> None:
    recorder = _FakeCallRecorder()
    service = _service(recorder)

    result = await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
        workflow_id="wf_1",
        step_id="step_1",
        agent_id="pack.agent",
    )

    assert len(recorder.record_calls) == 1
    call = recorder.record_calls[0]
    assert call["workflow_id"] == "wf_1"
    assert call["step_id"] == "step_1"
    assert call["agent_id"] == "pack.agent"
    assert call["prompt_id"] == "prompt_greeting"
    assert call["prompt_version"] == "1.0.0"
    assert call["response"] is result.response


@pytest.mark.asyncio
async def test_no_recording_is_attempted_without_a_recorder() -> None:
    service = _service(call_recorder=None)

    await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
        workflow_id="wf_1",
        step_id="step_1",
    )
    # No recorder configured -- nothing to assert on but that this didn't raise.


@pytest.mark.asyncio
async def test_no_recording_is_attempted_without_workflow_and_step_context() -> None:
    recorder = _FakeCallRecorder()
    service = _service(recorder)

    await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
    )

    assert recorder.record_calls == []


@pytest.mark.asyncio
async def test_the_llm_request_carries_a_trace_context_when_workflow_or_step_is_given() -> None:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})
    gateway = _RequestCapturingGateway()
    service = PromptedCompletionService(prompt_engine=engine, llm_gateway=gateway)

    await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
        workflow_id="wf_1",
        step_id="step_1",
    )

    assert gateway.last_request is not None
    assert gateway.last_request.metadata == TraceContext(workflow_id="wf_1", step_id="step_1")


@pytest.mark.asyncio
async def test_the_llm_request_has_no_metadata_when_neither_workflow_nor_step_is_given() -> None:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})
    gateway = _RequestCapturingGateway()
    service = PromptedCompletionService(prompt_engine=engine, llm_gateway=gateway)

    await service.complete_from_prompt(
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        variables={"name": "Ada"},
        model_alias="fast-cheap",
        max_output_tokens=100,
    )

    assert gateway.last_request is not None
    assert gateway.last_request.metadata is None


# --- build_anthropic_prompted_completion_service: construction-time wiring -


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_wires_the_real_components() -> None:
    # Never connected — engine construction and the components built from
    # it are lazy, so this exercises real wiring with no real I/O.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service, PromptedCompletionService)
    assert isinstance(service._prompt_engine, SqlPromptCatalog)
    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert isinstance(service._llm_gateway._gateways[PROVIDER_NAME], AnthropicAdapter)
    assert isinstance(service._call_recorder, SqlLLMCallRecorder)


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_merges_additional_gateways() -> None:
    # The specific capability this step adds: a second real provider
    # adapter registers into the identical DispatchingLLMGateway this
    # factory always builds, without displacing the Anthropic adapter
    # it always builds too.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    second_gateway = EchoLLMGateway()

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
        additional_gateways={"local": second_gateway},
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert isinstance(service._llm_gateway._gateways[PROVIDER_NAME], AnthropicAdapter)
    assert service._llm_gateway._gateways["local"] is second_gateway


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_threads_the_circuit_breaker() -> None:
    # A new, defaulted-None parameter — every existing caller that never
    # passes it (both tests above) gets circuit_breaker=None, unchanged.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    breaker = InMemoryCircuitBreaker(failure_threshold=5, reset_timeout_seconds=30.0)

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
        circuit_breaker=breaker,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._circuit_breaker is breaker


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_defaults_to_no_circuit_breaker() -> None:
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._circuit_breaker is None


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_threads_the_backoff_policy() -> None:
    # A new, defaulted-None parameter — every existing caller that never
    # passes it (every test above) gets backoff_policy=None, unchanged.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    policy = BackoffPolicy(
        max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=8.0, max_total_seconds=15.0
    )

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
        backoff_policy=policy,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._backoff_policy is policy


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_defaults_to_no_backoff_policy() -> None:
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._backoff_policy is None


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_threads_the_budget_enforcer() -> None:
    # A new, defaulted-None parameter — every existing caller that never
    # passes it (every test above) gets budget_enforcer=None, unchanged.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("10.00"))

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
        budget_enforcer=enforcer,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._budget_enforcer is enforcer


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_defaults_to_no_budget_enforcer() -> None:
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._budget_enforcer is None


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_threads_workflow_budget_enforcer() -> (
    None
):
    # A new, defaulted-None parameter — every existing caller that never
    # passes it (every test above) gets workflow_budget_enforcer=None,
    # unchanged.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    enforcer = PerScopeBudgetEnforcer(ceiling_usd=Decimal("25.00"))

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
        workflow_budget_enforcer=enforcer,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._workflow_budget_enforcer is enforcer


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_defaults_to_no_workflow_enforcer() -> (
    None
):
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._workflow_budget_enforcer is None


def _capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        supports_tools=True,
        supports_parallel_tool_calls=True,
        supports_strict_tools=False,
        supports_structured_output=False,
        supports_streaming=True,
        supports_thinking=True,
        supports_effort=True,
        supports_prompt_caching=True,
        prompt_cache_min_tokens=1024,
        supports_vision=True,
        max_input_tokens=1_000_000,
        max_output_tokens=8192,
        accepts_sampling_params=False,
    )


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_threads_the_capability_negotiator() -> (
    None
):
    # A new, defaulted-None parameter — every existing caller that never
    # passes it (every test above) gets capability_negotiator=None,
    # unchanged.
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}
    router = StaticRouter(
        routes={
            "coding-balanced": RoutingDecision(provider=PROVIDER_NAME, model_id="claude-sonnet-5")
        }
    )
    negotiator = StaticCapabilityNegotiator(
        router=router, capabilities_by_model_id={"claude-sonnet-5": _capabilities()}
    )

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=router,
        pricing=pricing,
        capability_negotiator=negotiator,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._capability_negotiator is negotiator


@pytest.mark.asyncio
async def test_build_anthropic_prompted_completion_service_defaults_to_no_negotiator() -> None:
    engine = create_async_engine("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    pricing = {"claude-sonnet-5": ModelPricing(input_per_million_usd=3, output_per_million_usd=15)}

    service = await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key"}),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=StaticRouter(
            routes={
                "coding-balanced": RoutingDecision(
                    provider=PROVIDER_NAME, model_id="claude-sonnet-5"
                )
            }
        ),
        pricing=pricing,
    )

    assert isinstance(service._llm_gateway, DispatchingLLMGateway)
    assert service._llm_gateway._capability_negotiator is None
