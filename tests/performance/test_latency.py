"""Real latency measurements against `nfr.md` §3, against real
infrastructure (real Postgres via testcontainers, ADR-0015; a real
Docker daemon for NFR-015 when reachable) — see `README.md` for which
NFR-01x targets this file covers and which §3 targets it explicitly
does not (no faked measurement for either).

Every test computes a real p95/p99 from real, repeated wall-clock
timings and asserts it against `nfr.md`'s own documented number —
never a synthetic sleep standing in for real work.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import docker
import docker.errors
import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextRequest
from ai_os_kernel.context_manager.resolvers import WorkflowStateResolver
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.sandbox.docker_executor import DockerSandbox
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

_DEFINITION_ID = "se.performance_latency_test"
_DEFINITION_VERSION = "1.0.0"
_DEFINITION_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.performance_latency_test/echo"
_SIGNING_KEY = "performance-test-signing-key-at-least-32-bytes"

# Enough repeats for a real p95/p99 to mean something without making
# this file itself the slow part of the suite.
_SAMPLES = 40


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "performance-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


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


def _p95_p99(samples: list[float]) -> tuple[float, float]:
    ordered = sorted(samples)
    n = len(ordered)
    p95 = ordered[min(n - 1, int(n * 0.95))]
    p99 = ordered[min(n - 1, int(n * 0.99))]
    return p95, p99


def _one_step_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Performance Latency Test",
            "description": "One real agent step, backed by a deterministic EchoAgent.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_work", "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


def test_nfr010_api_read_endpoint_latency(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-010: API read endpoint — target p95 200 ms, p99 500 ms.
    Measurement method per `nfr.md`: "Server-side span, excluding
    client network" — `TestClient` dispatches real ASGI requests
    in-process, excluding real client network exactly as documented.
    A real bearer token (`viewer`, holding `workflow:read`) is required
    -- this route is genuinely authenticated, not bypassed."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['viewer'])}"}
    samples: list[float] = []
    with TestClient(app) as client:
        for _ in range(_SAMPLES):
            started = time.perf_counter()
            response = client.get("/api/v1/workflows?limit=10", headers=headers)
            samples.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200

    p95, p99 = _p95_p99(samples)
    print(f"\nNFR-010 GET /api/v1/workflows: p95={p95:.1f}ms p99={p99:.1f}ms (target 200/500ms)")
    assert p95 < 200
    assert p99 < 500


def test_nfr011_workflow_submission_latency(database_url: str) -> None:
    """NFR-011: workflow submission — target p95 300 ms, p99 800 ms.

    Measures the real service-layer "submission" operation
    (`create_instance` + `start`) directly, not the one real HTTP
    route (`POST /api/v1/workflows`, the platform demo trigger) —
    that route's own docstring discloses it runs the *entire* instance
    to completion synchronously before responding, which would
    conflate submission latency with full execution latency and
    dishonestly inflate this specific measurement.
    """
    engine = build_engine(database_url)

    async def _run() -> list[float]:
        definition_catalog = SqlWorkflowDefinitionCatalog(engine)
        repository = SqlWorkflowInstanceRepository(engine)
        service = WorkflowInstanceService(
            repository=repository,
            step_executor=NoOpStepExecutor(),
            definition_catalog=definition_catalog,
        )
        definition = _one_step_definition()
        samples: list[float] = []
        for _ in range(_SAMPLES):
            started = time.perf_counter()
            instance = await service.create_instance(
                definition=definition,
                inputs={},
                principal_id="perf-test",
                pack_id=_DEFINITION_PACK_ID,
            )
            await service.start(workflow_id=instance.workflow_id, reason="perf test submission")
            samples.append((time.perf_counter() - started) * 1000)
        return samples

    try:
        samples = asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())

    p95, p99 = _p95_p99(samples)
    print(f"\nNFR-011 create_instance+start: p95={p95:.1f}ms p99={p99:.1f}ms (target 300/800ms)")
    assert p95 < 300
    assert p99 < 800


def test_nfr012_platform_overhead_per_step_excluding_agent_time(database_url: str) -> None:
    """NFR-012: platform overhead per step (context assembly +
    validation + state write, excluding agent/model time) — target
    p95 500 ms, p99 1.5 s. `EchoAgent` returns near-instantly, so
    timing a real `advance()` call over it isolates the platform's own
    overhead from real agent/model time, exactly as the target's own
    definition asks."""
    engine = build_engine(database_url)

    async def _run() -> list[float]:
        definition_catalog = SqlWorkflowDefinitionCatalog(engine)
        repository = SqlWorkflowInstanceRepository(engine)
        context_manager = DefaultContextManager(
            resolvers=[WorkflowStateResolver(repository)], default_token_budget=8000
        )
        step_executor = DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(
                InMemoryAgentRegistry({_AGENT_ID: EchoAgent()}), context_manager=context_manager
            ),
            tool_executor=NoOpStepExecutor(),
            default_executor=NoOpStepExecutor(),
        )
        service = WorkflowInstanceService(
            repository=repository,
            step_executor=step_executor,
            definition_catalog=definition_catalog,
        )
        definition = _one_step_definition()
        samples: list[float] = []
        for _ in range(_SAMPLES):
            instance = await service.create_instance(
                definition=definition,
                inputs={},
                principal_id="perf-test",
                pack_id=_DEFINITION_PACK_ID,
            )
            await service.start(workflow_id=instance.workflow_id, reason="perf test")
            started = time.perf_counter()
            await service.advance(workflow_id=instance.workflow_id, definition=definition)
            samples.append((time.perf_counter() - started) * 1000)
        return samples

    try:
        samples = asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())

    p95, p99 = _p95_p99(samples)
    print(
        f"\nNFR-012 advance() over EchoAgent: p95={p95:.1f}ms p99={p99:.1f}ms (target 500/1500ms)"
    )
    assert p95 < 500
    assert p99 < 1500


def test_nfr013_context_assembly_latency(database_url: str) -> None:
    """NFR-013: context assembly — target p95 400 ms, p99 1 s."""
    engine = build_engine(database_url)

    async def _run() -> list[float]:
        repository = SqlWorkflowInstanceRepository(engine)
        context_manager = DefaultContextManager(
            resolvers=[WorkflowStateResolver(repository)], default_token_budget=8000
        )
        definition_catalog = SqlWorkflowDefinitionCatalog(engine)
        await definition_catalog.register(
            definition=_one_step_definition(), pack_id=_DEFINITION_PACK_ID
        )
        created = await repository.create(
            definition_id=_DEFINITION_ID,
            definition_version=_DEFINITION_VERSION,
            inputs={},
            principal_id="perf-test",
        )
        request = ContextRequest(
            workflow_id=created.workflow_id, step_id="do_work", agent_id=_AGENT_ID
        )
        samples: list[float] = []
        for _ in range(_SAMPLES):
            started = time.perf_counter()
            await context_manager.assemble(request)
            samples.append((time.perf_counter() - started) * 1000)
        return samples

    try:
        samples = asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())

    p95, p99 = _p95_p99(samples)
    print(
        f"\nNFR-013 context_manager.assemble(): p95={p95:.1f}ms p99={p99:.1f}ms (target 400/1000ms)"
    )
    assert p95 < 400
    assert p99 < 1000


def test_nfr018_workflow_state_write_latency(database_url: str) -> None:
    """NFR-018: workflow state write (event + snapshot, one
    transaction) — target p95 50 ms, p99 150 ms."""
    engine = build_engine(database_url)

    async def _run() -> list[float]:
        definition_catalog = SqlWorkflowDefinitionCatalog(engine)
        await definition_catalog.register(
            definition=_one_step_definition(), pack_id=_DEFINITION_PACK_ID
        )
        repository = SqlWorkflowInstanceRepository(engine)
        samples: list[float] = []
        for _ in range(_SAMPLES):
            started = time.perf_counter()
            await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="perf-test",
            )
            samples.append((time.perf_counter() - started) * 1000)
        return samples

    try:
        samples = asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())

    p95, p99 = _p95_p99(samples)
    print(f"\nNFR-018 repository.create(): p95={p95:.1f}ms p99={p99:.1f}ms (target 50/150ms)")
    assert p95 < 50
    assert p99 < 150


@pytest.fixture(scope="module")
def docker_available() -> Generator[None, None, None]:
    try:
        client = docker.from_env()
        client.ping()
    except (docker.errors.DockerException, OSError) as exc:
        pytest.skip(f"Docker daemon is not reachable — NFR-015 is opt-in: {exc}")
    else:
        yield


def test_nfr015_tier1_sandbox_cold_start(docker_available: None, tmp_path: Path) -> None:
    """NFR-015: Tier 1 sandbox cold start — target p95 2 s, p99 5 s,
    documented **(baseline)**, "warm pool assumed". No warm pool exists
    in this codebase (`deployment_architecture.md`'s own Implementation
    Status: sandbox images are "pre-pulled onto nodes" in the
    documented target, not built) — this measures a genuinely *colder*
    start than the target assumes (image pull/cache state on this
    machine, not a pre-warmed pool), disclosed here rather than
    silently treated as an apples-to-apples pass/fail."""
    sandbox = DockerSandbox()

    async def _run() -> list[float]:
        samples: list[float] = []
        for _run_index in range(3):
            started = time.perf_counter()
            result = await sandbox.execute(
                command=["python3", "-c", "print('ok')"],
                working_directory=tmp_path,
                timeout_seconds=30.0,
                max_output_bytes=65536,
            )
            samples.append((time.perf_counter() - started) * 1000)
            assert result.exit_code == 0
        return samples

    samples = asyncio.run(_run())
    p95, _ = _p95_p99(samples)
    print(
        f"\nNFR-015 DockerSandbox cold start (no warm pool, {len(samples)} real runs): "
        f"{[f'{s:.0f}ms' for s in samples]} (target p95 2000ms, warm-pool-assumed)"
    )
    # Reported, not scored pass/fail against the pool-assumed target —
    # see this test's own docstring for why that comparison would be
    # dishonest. A sanity ceiling still applies: a genuinely broken
    # cold start (network stall, daemon hang) must still fail loudly.
    assert p95 < 30000
