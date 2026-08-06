"""Real, end-to-end proof of this step's own deliverable: a fresh
Kernel startup (``ai_os_kernel.bootstrap.build_app()`` + ``_lifespan``)
against a real, empty database, pointed at the real, on-disk
``capability_packs/`` tree, genuinely discovers, registers, and
activates the real Software Engineering pack — with **no manual
``register()``/``activate()`` call anywhere in this test file**
(contrast every other integration test in this pack's own history,
which all call a hand-written ``_register_and_activate_pack`` helper;
see ``ai_os_kernel.bootstrap``'s own docstring for the real composition
that now makes such a helper unnecessary for a real Kernel process).

**Deliberately does not set ``capability_pack_dirs=[]``** — every other
integration test in this suite does, to stay isolated from the real
``capability_packs/`` tree (see
``tests/unit/kernel/entrypoints/test_api.py``'s own comment: "isolated
from the real capability_packs/ tree"). This file's whole point is to
prove the *un-isolated*, real path: pytest's own working directory is
the repository root (the same "every documented way of running the
Kernel starts the process from the repository root" assumption
``bootstrap.py``'s own docstring states), so ``PlatformConfig``'s own
default ``capability_pack_dirs`` (``["capability_packs"]``) resolves to
the real, on-disk tree — which today contains both the real
``software-engineering`` pack and the schema-valid, capability-less
``_template`` example pack. Both are asserted on below: the second as
proof that a manifest declaring no agents/prompts/tools registers and
activates cleanly, deriving zero catalog rows, not a special case this
step had to add error handling for.

No live Anthropic credential is used or required anywhere in this file:
the QA/Test Agent (``qa-test``) makes no LLM call at all, so it alone is
enough to prove a genuinely auto-registered agent can genuinely resolve
and run end to end without one — the identical "no live credential
needed" precedent
``tests/integration/workflow_engine/test_verification_agent_pack.py``
already established. The real HTTP trigger route is also exercised
without a live credential, proving *resolution* now succeeds — a
materially different, deeper failure than
``tests/integration/test_delivery_pipeline_route.py``'s own
identical-looking, deliberately isolated (``capability_pack_dirs=[]``)
test, which fails at "no agent registered" since no catalog rows exist
there at all.

The four tests below share one module-scoped, real Postgres database
(ADR-0015, testcontainers). The first proves a genuinely fresh
first-time discovery; the second is a genuine second "Kernel restart"
against that same, already-populated database — real proof of
idempotency, not a simulated one.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.catalog_schema import agents as agents_table
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.workflow_engine.pack_state import PackState
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_pack_software_engineering.agents.verification import (
    TestAgentEntrypoint,
    TestAgentOutput,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "pack-discovery-test-signing-key-at-least-32-bytes"
_ROUTE = "/api/v1/workflows/se.delivery_pipeline"
_PACK_ID = "software-engineering"
_REAL_AGENT_IDS = {
    f"{_PACK_ID}/requirements-analyst",
    f"{_PACK_ID}/architecture",
    f"{_PACK_ID}/build",
    f"{_PACK_ID}/lint",
    f"{_PACK_ID}/qa-test",
    f"{_PACK_ID}/documentation",
    f"{_PACK_ID}/database",
    f"{_PACK_ID}/api-designer",
    f"{_PACK_ID}/security-analysis",
    f"{_PACK_ID}/git-push",
}


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


def _config() -> PlatformConfig:
    # Deliberately NOT capability_pack_dirs=[] — see this module's own
    # docstring for why this suite's one integration test stays
    # un-isolated from the real capability_packs/ tree on purpose.
    return PlatformConfig(env="test", role="api", manifest_schema_path=SCHEMA_PATH)


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "pack-discovery-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_a_fresh_kernel_startup_genuinely_registers_and_activates_the_real_pack(
    database_url: str,
) -> None:
    """No manual register()/activate() call anywhere in this test —
    _lifespan's own real pack discovery does it, against a genuinely
    empty database."""
    app = build_app(_config())

    with TestClient(app):
        pass  # _lifespan already did the real discovery/registration/activation

    # A dedicated engine, built and used entirely after the TestClient
    # block above has fully exited (so _lifespan's own internal engine
    # is already disposed) and entirely within one asyncio.run() call —
    # deliberately never mixing this test's own event loop with
    # TestClient's own lifespan-management loop, which is genuinely
    # unsafe to nest reliably (a real, discovered flake this step's own
    # first draft hit: asyncpg connections are bound to the loop that
    # created them, and pool_pre_ping's own checkout-time ping against a
    # connection from a different, already-closed loop raises).
    engine = build_engine(database_url)

    async def _run() -> None:
        try:
            repository = SqlPackLifecycleRepository(engine)
            record = await repository.get_pack(_PACK_ID)
            assert record is not None
            assert record.state is PackState.ACTIVATED

            # The schema-valid, capability-less example pack registers
            # and activates cleanly too — proof that a manifest
            # declaring no agents/prompts/tools derives zero rows
            # without error, not a case this step had to special-case.
            template_record = await repository.get_pack("template-pack")
            assert template_record is not None
            assert template_record.state is PackState.ACTIVATED

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(agents_table.c.agent_id).where(agents_table.c.pack_id == _PACK_ID)
                )
                agent_ids = {row.agent_id for row in result}
            assert agent_ids == _REAL_AGENT_IDS
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_second_kernel_startup_against_the_same_database_is_idempotent(
    database_url: str,
) -> None:
    """A real 'Kernel restart' against the same, already-populated
    database — the register()/activate() calls the previous test's own
    _lifespan already made for real. Must not raise, must not duplicate
    any catalog.agents rows, and the pack must still end up ACTIVATED —
    not left in some intermediate state by the caught-and-logged
    idempotent-skip path bootstrap.py's own docstring describes."""
    app = build_app(_config())

    with TestClient(app):
        pass  # a genuine second startup — _lifespan's own idempotent-skip path runs here

    # Built and used entirely after TestClient's own block exits, in one
    # asyncio.run() call — see the previous test's own comment for why.
    engine = build_engine(database_url)

    async def _run() -> None:
        try:
            repository = SqlPackLifecycleRepository(engine)
            record = await repository.get_pack(_PACK_ID)
            assert record is not None
            assert record.state is PackState.ACTIVATED

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(sa.func.count())
                    .select_from(agents_table)
                    .where(agents_table.c.pack_id == _PACK_ID)
                )
                count = result.scalar_one()
            assert count == len(_REAL_AGENT_IDS)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_auto_registered_qa_test_agent_genuinely_resolves_and_runs(
    tmp_path: Path, database_url: str
) -> None:
    """No live Anthropic credential needed — qa-test makes no LLM call
    at all, the identical precedent test_verification_agent_pack.py
    already established. Proves the pack's agents (not just its own
    catalog.packs row) are genuinely resolvable and genuinely runnable
    through SqlAgentRegistry after nothing but a real Kernel startup —
    still no manual register()/activate() call anywhere in this test."""
    app = build_app(_config())
    with TestClient(app):
        pass  # _lifespan already did the real discovery/registration/activation

    (tmp_path / "ok.py").write_text("print('pack discovery pass')\n", encoding="utf-8")

    # The identical "caller builds and keeps its own sandbox reference"
    # pattern test_verification_agent_pack.py already established — a
    # generic ToolInvoker/SqlAgentRegistry default carries no
    # python_command concept, so the caller supplies its own real
    # sandbox and reuses its own real interpreter command.
    sandbox = build_default_sandbox_executor()
    python_command = list(sandbox.python_command)

    engine = build_engine(database_url)
    try:

        async def _run() -> None:
            registry = SqlAgentRegistry(engine, sandbox=sandbox)
            resolved = await registry.resolve_agent(f"{_PACK_ID}/qa-test")
            assert isinstance(resolved, TestAgentEntrypoint)

            outputs = await resolved.execute(
                {
                    "workingDirectory": str(tmp_path),
                    "filePath": "ok.py",
                    "runCommand": [*python_command, "ok.py"],
                }
            )
            TestAgentOutput.model_validate(outputs)
            assert outputs["passed"] is True
            assert outputs["exitCode"] == 0

        asyncio.run(_run())
    finally:
        asyncio.run(engine.dispose())


def test_the_real_pipeline_route_genuinely_resolves_agents_via_auto_registration(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No manual register()/activate() call anywhere in this test — the
    real, _lifespan-driven discovery is what makes agent resolution
    succeed at all. Without a live Anthropic credential the pipeline
    still cannot complete, but now for a materially different, deeper
    reason than tests/integration/test_delivery_pipeline_route.py's own
    identical-looking test (which deliberately stays isolated via
    capability_pack_dirs=[]): there, Requirements Analyst is never even
    in the catalog ("no agent registered"); here, it genuinely resolves
    and only then fails, because no llm_gateway is configured — real
    proof that genuine catalog rows, not merely the route's own
    plumbing, are what changed this step."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "failed"
    assert body["error"]
    assert "no agent registered" not in body["error"]
    assert "llm_gateway" in body["error"]
