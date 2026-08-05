"""Deterministic, real-database verification of this step's own
deliverable: ``bootstrap._build_workflow_trigger`` genuinely drives the
demo :class:`~ai_os_kernel.workflow_engine.models.WorkflowDefinition`
through create -> start -> run-to-completion, and a step declaring
``agentId="platform/prompted-agent"`` really is dispatched to whatever
agent the caller registered under that id.

Deliberately substitutes a hand-built, Echo-backed
:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent` for
the real Anthropic-backed one ``_build_prompted_agent_registry``
constructs at real startup — this file proves the Workflow Engine
machinery itself (persistence, leasing, step dispatch, agent
resolution, output validation) genuinely works, without requiring a
live Anthropic credential. The opt-in live counterpart,
``test_bootstrap_workflow_trigger_live.py``, proves the same path
through the real composition root with a real completion.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.bootstrap import (
    _DEMO_WORKFLOW_PROMPT_ID,
    _DEMO_WORKFLOW_PROMPT_VERSION,
    _MEMORY_RESOLVER_LIMIT,
    _MEMORY_RESOLVER_TYPE,
    _PROMPTED_AGENT_ID,
    _RUNTIME_CONTEXT_CONFIG_KEYS,
    _build_workflow_trigger,
)
from ai_os_kernel.configuration_manager import ConfigurationManager, RuntimeOverrideStore
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.resolvers import (
    MemoryResolver,
    RuntimeConfigResolver,
    WorkflowStateResolver,
)
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.memory_writer import SqlMemoryStore
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.errors import AgentNotRegisteredError
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_GREETING_TEMPLATE = "Hello from the smoke test!"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _echo_agent_registry() -> InMemoryAgentRegistry:
    prompt_engine = InMemoryPromptEngine(
        {(_DEMO_WORKFLOW_PROMPT_ID, _DEMO_WORKFLOW_PROMPT_VERSION): _GREETING_TEMPLATE}
    )
    service = PromptedCompletionService(prompt_engine=prompt_engine, llm_gateway=EchoLLMGateway())
    agent = PromptedAgent(service=service, max_output_tokens=1024)
    return InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})


def _context_manager(
    engine: AsyncEngine, *, token_budget: int | None = None
) -> DefaultContextManager:
    return DefaultContextManager(
        resolvers=[WorkflowStateResolver(SqlWorkflowInstanceRepository(engine))],
        default_token_budget=token_budget,
    )


def test_the_demo_workflow_reaches_a_registered_prompted_agent(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = _build_workflow_trigger(
                engine, _echo_agent_registry(), _context_manager(engine)
            )

            result = await trigger({}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            assert result.last_instance is not None
            assert result.last_instance.status is WorkflowInstanceStatus.COMPLETED

            steps = await SqlWorkflowInstanceRepository(engine).list_steps(result.workflow_id)
            assert len(steps) == 1
            assert steps[0].agent_id == _PROMPTED_AGENT_ID
            assert steps[0].outputs == {"content": _GREETING_TEMPLATE}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_demo_workflow_fails_clearly_when_the_agent_is_not_registered(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = _build_workflow_trigger(
                engine, InMemoryAgentRegistry({}), _context_manager(engine)
            )

            result = await trigger({}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.FAILED
            assert isinstance(result.error, AgentNotRegisteredError)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _context_manager_with_runtime_config(engine: AsyncEngine) -> DefaultContextManager:
    # The real, production-shaped composition P02-S03-M08-T11 adds to
    # _lifespan/build_workflow_worker_loop -- a real ConfigurationManager
    # against this repo's own real config/platform.yaml + a real,
    # valid environment file (infra/environments/local.yaml), not a
    # tmp_path fixture, proving the production wiring itself, not just
    # RuntimeConfigResolver in isolation (already proven in
    # tests/unit/kernel/context_manager/test_runtime_config_resolver.py).
    configuration_manager = ConfigurationManager(
        environment="local",
        platform_config_path=REPO_ROOT / "config" / "platform.yaml",
        environments_dir=REPO_ROOT / "infra" / "environments",
    )
    return DefaultContextManager(
        resolvers=[
            WorkflowStateResolver(SqlWorkflowInstanceRepository(engine)),
            RuntimeConfigResolver(
                configuration_manager=configuration_manager,
                runtime_override_store=RuntimeOverrideStore(),
                role="api",
                config_keys=_RUNTIME_CONTEXT_CONFIG_KEYS,
            ),
        ],
    )


def _context_aware_agent_registry() -> InMemoryAgentRegistry:
    prompt_engine = InMemoryPromptEngine(
        {(_DEMO_WORKFLOW_PROMPT_ID, _DEMO_WORKFLOW_PROMPT_VERSION): "Task: {{context}}"}
    )
    service = PromptedCompletionService(prompt_engine=prompt_engine, llm_gateway=EchoLLMGateway())
    agent = PromptedAgent(service=service, max_output_tokens=1024)
    return InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})


def test_the_demo_workflow_agent_receives_real_assembled_context_from_a_real_database(
    database_url: str,
) -> None:
    # The Context Manager's own end-to-end proof: a real
    # WorkflowStateResolver reads this instance's own `inputs` back from
    # a real Postgres row (not a stub), AgentStepExecutor assembles it
    # into a real AssembledContext, and PromptedAgent flattens it into
    # the rendered prompt — genuinely, not by construction.
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = _build_workflow_trigger(
                engine, _context_aware_agent_registry(), _context_manager(engine)
            )

            result = await trigger({"task": "write tests"}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            steps = await SqlWorkflowInstanceRepository(engine).list_steps(result.workflow_id)
            assert len(steps) == 1
            outputs = steps[0].outputs
            assert outputs is not None
            assert '"task": "write tests"' in outputs["content"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_runtime_config_flows_into_a_real_agent_step_via_the_production_wiring(
    database_url: str,
) -> None:
    # P02-S03-M08-T11's own proof: the same real DefaultContextManager
    # shape _lifespan/build_workflow_worker_loop now construct in
    # production (WorkflowStateResolver + RuntimeConfigResolver
    # together) genuinely puts real runtime configuration into a real
    # agent's rendered prompt, through the real _build_workflow_trigger
    # path -- not RuntimeConfigResolver exercised standalone.
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = _build_workflow_trigger(
                engine,
                _context_aware_agent_registry(),
                _context_manager_with_runtime_config(engine),
            )

            result = await trigger({"task": "write tests"}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            steps = await SqlWorkflowInstanceRepository(engine).list_steps(result.workflow_id)
            assert len(steps) == 1
            outputs = steps[0].outputs
            assert outputs is not None
            content = outputs["content"]
            # Both real sources present in one real, assembled context:
            # the workflow's own inputs (WorkflowStateResolver, proven
            # already above) and now real runtime configuration too.
            assert '"task": "write tests"' in content
            assert 'env: "local"' in content
            assert 'role: "api"' in content
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _ensure_workflow_definition_registered(
    engine: AsyncEngine, *, definition_id: str, version: str
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, version, pack_id, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, :version, 'test.pack', '{}'::jsonb, "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {"definition_id": definition_id, "version": version},
        )


async def _create_a_prior_real_workflow_instance(engine: AsyncEngine) -> str:
    # A real workflow_instances row genuinely distinct from the demo
    # workflow the test below triggers -- satisfies memory_items' own
    # real FK to workflow_instances, and proves MemoryResolver's own
    # cross-run behaviour: memory written under this instance must
    # still surface in a completely different, later-triggered run.
    definition_id = "test.memory-prior-workflow"
    version = "1.0.0"
    await _ensure_workflow_definition_registered(
        engine, definition_id=definition_id, version=version
    )
    instance = await SqlWorkflowInstanceRepository(engine).create(
        definition_id=definition_id,
        definition_version=version,
        inputs={},
        principal_id="test-principal",
    )
    return instance.workflow_id


def _context_manager_with_memory(
    engine: AsyncEngine, memory_store: SqlMemoryStore
) -> DefaultContextManager:
    # The real, production-shaped composition P02-S03-M08-T13 adds to
    # _lifespan/build_workflow_worker_loop -- WorkflowStateResolver +
    # MemoryResolver together, proving the production wiring itself,
    # not just MemoryResolver in isolation (already proven in
    # tests/integration/context_manager/test_memory_resolver.py).
    return DefaultContextManager(
        resolvers=[
            WorkflowStateResolver(SqlWorkflowInstanceRepository(engine)),
            MemoryResolver(
                memory_store=memory_store,
                memory_type=_MEMORY_RESOLVER_TYPE,
                limit=_MEMORY_RESOLVER_LIMIT,
            ),
        ]
    )


def test_memory_flows_into_a_real_agent_step_via_the_production_wiring(
    database_url: str,
) -> None:
    # P02-S03-M08-T13's own proof: the same real DefaultContextManager
    # shape _lifespan/build_workflow_worker_loop now construct in
    # production (WorkflowStateResolver + MemoryResolver together)
    # genuinely puts real, persisted, cross-run memory into a real
    # agent's rendered prompt, through the real _build_workflow_trigger
    # path -- not MemoryResolver exercised standalone.
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            memory_store = SqlMemoryStore(engine)
            prior_workflow_id = await _create_a_prior_real_workflow_instance(engine)
            written = await memory_store.write_memory(
                memory_type=_MEMORY_RESOLVER_TYPE,
                content="past run learned: retry writes with exponential backoff",
                source_workflow_id=prior_workflow_id,
            )

            trigger = _build_workflow_trigger(
                engine,
                _context_aware_agent_registry(),
                _context_manager_with_memory(engine, memory_store),
            )

            result = await trigger({"task": "write tests"}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            steps = await SqlWorkflowInstanceRepository(engine).list_steps(result.workflow_id)
            assert len(steps) == 1
            outputs = steps[0].outputs
            assert outputs is not None
            content = outputs["content"]
            # Both real sources present in one real, assembled context:
            # this run's own inputs (WorkflowStateResolver) and a
            # different, prior run's own real, persisted memory
            # (MemoryResolver) -- genuinely cross-run, not scoped to
            # result.workflow_id.
            assert '"task": "write tests"' in content
            assert "past run learned: retry writes with exponential backoff" in content
            assert written.source_workflow_id != result.workflow_id
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_real_token_budget_excludes_a_real_oversized_item_from_a_real_database(
    database_url: str,
) -> None:
    # The Size & Token Budget Enforcer's own end-to-end proof: a real
    # WorkflowStateResolver item, read back from a real Postgres row, is
    # genuinely excluded once it no longer fits the assembler's real
    # configured budget — proving exclusion, not just its absence.
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = _build_workflow_trigger(
                engine,
                _context_aware_agent_registry(),
                _context_manager(engine, token_budget=1),
            )

            result = await trigger({"task": "write a lot of tests please"}, "test-principal")

            # The one real item (this workflow's own `inputs`) does not
            # fit inside a 1-token budget, so it is excluded entirely;
            # "context" is then a required-but-unsupplied prompt
            # variable, and the step genuinely fails — not silently
            # renders without it.
            assert result.outcome is WorkflowRunOutcome.FAILED
        finally:
            await engine.dispose()

    asyncio.run(_run())
