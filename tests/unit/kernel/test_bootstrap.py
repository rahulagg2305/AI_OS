"""Unit tests for the composition root's real-startup wiring
(``bootstrap._lifespan``): the ``PromptedAgent`` registration path, not
the routes already covered by ``tests/unit/kernel/entrypoints/test_api.py``.

Covers both halves of this step's own design: *degrade gracefully*
(no real database, no real network, no real secret — proves an
unconfigured environment still starts the Kernel and answers health
checks rather than crashing, exactly like ``manifest_loader_check``'s
own existing try/except) and *construct for real* (a syntactically
valid but never-connected database URL plus a fake-but-present secret —
proves the success path actually builds a working ``PromptedAgent``,
without touching real network or a real database; mirrors
``tests/unit/kernel/test_prompted_completion.py``'s own
never-connected-engine technique).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.resolvers import RuntimeConfigResolver, WorkflowStateResolver
from ai_os_kernel.llm_gateway.backoff import BackoffPolicy
from ai_os_kernel.llm_gateway.budget_enforcer import PerScopeBudgetEnforcer
from ai_os_kernel.llm_gateway.capability_negotiator import StaticCapabilityNegotiator
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.errors import AgentNotRegisteredError
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def test_agent_registry_degrades_to_empty_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neither a real database nor a real secret is configured in this
    # test environment — the exact "Stage B integration absent" case
    # this step's own degrade-gracefully design targets.
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app):
        registry = app.state.agent_registry
        assert isinstance(registry, InMemoryAgentRegistry)

        with pytest.raises(AgentNotRegisteredError):
            asyncio.run(registry.resolve_agent("platform/prompted-agent"))


def test_agent_registry_registers_a_real_prompted_agent_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Never connected — engine construction is lazy, and secret
    # resolution/AnthropicAdapter/AsyncAnthropic construction do no
    # network I/O either, only complete() does — so this exercises the
    # real success path with no real infrastructure.
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        registry = app.state.agent_registry
        agent = asyncio.run(registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)


def test_the_real_composition_root_builds_coding_strongs_configured_fallback_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # config/llm.yaml declares a real, live-by-default fallback for
    # "coding-strong" (anthropic claude-opus-5 -> anthropic
    # claude-sonnet-5) — this proves kernel/bootstrap.py's own
    # build_routing_chain wiring runs against the real, checked-in
    # configuration file, not just a hand-built test router.
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    assert isinstance(agent._service._llm_gateway, DispatchingLLMGateway)
    decision = agent._service._llm_gateway._router.resolve("coding-strong")
    assert decision.provider == "anthropic"
    assert decision.model_id == "claude-opus-5"
    assert decision.fallback is not None
    assert decision.fallback.provider == "anthropic"
    assert decision.fallback.model_id == "claude-sonnet-5"
    assert decision.fallback.fallback is None


def test_the_real_composition_root_wires_a_real_circuit_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    assert isinstance(agent._service._llm_gateway, DispatchingLLMGateway)
    assert isinstance(agent._service._llm_gateway._circuit_breaker, InMemoryCircuitBreaker)


def test_the_real_composition_root_wires_a_real_backoff_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    assert isinstance(agent._service._llm_gateway, DispatchingLLMGateway)
    assert isinstance(agent._service._llm_gateway._backoff_policy, BackoffPolicy)


def test_the_real_composition_root_wires_a_real_budget_enforcer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    assert isinstance(agent._service._llm_gateway, DispatchingLLMGateway)
    assert isinstance(agent._service._llm_gateway._budget_enforcer, PerScopeBudgetEnforcer)


def test_the_real_composition_root_wires_a_real_workflow_budget_enforcer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    gateway = agent._service._llm_gateway
    assert isinstance(gateway, DispatchingLLMGateway)
    assert isinstance(gateway._workflow_budget_enforcer, PerScopeBudgetEnforcer)
    # The two ceilings are independent instances with independent scope
    # spaces, not one enforcer reused for both purposes.
    assert gateway._workflow_budget_enforcer is not gateway._budget_enforcer


def test_the_real_composition_root_wires_a_real_capability_negotiator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    app = build_app(_config())

    with TestClient(app):
        agent = asyncio.run(app.state.agent_registry.resolve_agent("platform/prompted-agent"))

    assert isinstance(agent, PromptedAgent)
    assert isinstance(agent._service, PromptedCompletionService)
    gateway = agent._service._llm_gateway
    assert isinstance(gateway, DispatchingLLMGateway)
    assert isinstance(gateway._capability_negotiator, StaticCapabilityNegotiator)
    # config/llm.yaml's own real capabilities: section — a real,
    # positive fact about a real, checked-in model, not a stub.
    capabilities = gateway.capabilities("coding-balanced")
    assert capabilities.supports_tools is True
    assert capabilities.max_input_tokens > 0


def test_the_real_composition_root_wires_a_real_context_manager_with_a_token_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    monkeypatch.setenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", "test-key-value")
    # RuntimeConfigResolver's own wiring (below) resolves a real
    # ConfigurationManager off a fresh BootstrapEnv() read -- this
    # suite's own CI workflow sets the real AIOS_ENV to "ci", not one
    # of ConfigurationManager's real, documented environments, so this
    # assertion pins a real, valid one deterministically rather than
    # depending on whatever the ambient shell happens to have.
    monkeypatch.setenv("AIOS_ENV", "local")
    app = build_app(_config())

    with TestClient(app):
        context_manager = app.state.context_manager

    assert isinstance(context_manager, DefaultContextManager)
    assert isinstance(context_manager._resolvers[0], WorkflowStateResolver)
    # P02-S03-M08-T11: RuntimeConfigResolver now rides alongside it in
    # the real production composition -- previously wired nowhere.
    assert isinstance(context_manager._resolvers[1], RuntimeConfigResolver)
    assert context_manager._default_token_budget is not None
    assert context_manager._default_token_budget > 0


def test_bare_test_client_never_triggers_the_lifespan_at_all() -> None:
    # The behaviour every existing bare-TestClient health-check test
    # already relies on, verified explicitly here rather than only
    # implied — see bootstrap._lifespan's own docstring.
    app = build_app(_config())
    client = TestClient(app)

    client.get("/api/v1/health/live")

    assert not hasattr(app.state, "agent_registry")


def test_pack_lifecycle_repository_is_absent_when_the_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The identical "no real engine, nothing real to run against"
    # degrade path workflow_instance_repository already follows — see
    # bootstrap._lifespan's own docstring.
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app):
        assert not hasattr(app.state, "pack_lifecycle_repository")


def test_pack_lifecycle_repository_is_a_real_repository_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Never connected — engine construction is lazy, the same technique
    # test_agent_registry_registers_a_real_prompted_agent_when_configured
    # above already uses — so this exercises the real construction path
    # with no real infrastructure. The genuinely-connected path (a real
    # register()/activate()/deactivate() call) is covered by
    # tests/integration/capability_manager/test_bootstrap_pack_lifecycle.py.
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    app = build_app(_config())

    with TestClient(app):
        repository = app.state.pack_lifecycle_repository

    assert isinstance(repository, SqlPackLifecycleRepository)
