"""The third real, end-to-end proof in the `software-engineering`
pack's own history: the Test Agent, registered and activated through
the real `SqlPackLifecycleRepository`, resolved through the real
`SqlAgentRegistry` — the identical pattern
`test_architecture_agent_pack.py`/`test_build_agent_pack.py` already
proved for their own agents.

**This agent needs no live provider credentials at all — a genuine,
discovered difference from its two pack-mates, not an oversight.** The
Test Agent makes no LLM call (see its own module's docstring for why),
so unlike `test_architecture_agent_pack.py`/`test_build_agent_pack.py`,
there is no opt-in-live tier gated on `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`
here — every test in this file needs only a real Postgres container
(ADR-0015) and runs unconditionally once Docker Desktop is available.
"""

import asyncio
import contextlib
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_pack_software_engineering.agents.verification import (
    TestAgentEntrypoint,
    TestAgentOutput,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/qa-test"
_AGENT_ENTRYPOINT = "ai_os_pack_software_engineering.agents.verification:TestAgentEntrypoint"


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


async def _register_and_activate_pack(database_url: str) -> None:
    """Idempotent — mirrors test_architecture_agent_pack.py's/
    test_build_agent_pack.py's own helper exactly."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (REPO_ROOT / "capability_packs" / "software-engineering" / "manifest.yaml").open(
            encoding="utf-8"
        ) as fh:
            manifest = yaml.safe_load(fh)
        with contextlib.suppress(CapabilityManagerError):
            await repository.register(
                pack_id=_PACK_ID,
                version=_PACK_VERSION,
                manifest=manifest,
                sdk_version=">=0.1.0,<1.0.0",
                min_kernel_version="0.1.0",
                actor="test",
                reason="test agent pack integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_row(database_url: str) -> None:
    """No automated manifest -> catalog.agents installer exists yet —
    mirrors this pack's own prior integration tests exactly."""
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, :pack_id, :version, :entrypoint, "
                    " '{}'::jsonb, '{}'::jsonb, '[\"sandbox:execute\"]'::jsonb, '[]'::jsonb) "
                    "ON CONFLICT (agent_id) DO NOTHING"
                ),
                {
                    "agent_id": _AGENT_ID,
                    "pack_id": _PACK_ID,
                    "version": _PACK_VERSION,
                    "entrypoint": _AGENT_ENTRYPOINT,
                },
            )
    finally:
        await engine.dispose()


def test_sql_agent_registry_genuinely_resolves_the_test_agent(database_url: str) -> None:
    """Deterministic. Proves the Test Agent is genuinely resolvable
    through SqlAgentRegistry — the same tension already closed for its
    two pack-mates."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, TestAgentEntrypoint)
            assert resolved.output_schema["required"] == ["passed", "exitCode", "output"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_real_workflow_step_genuinely_runs_a_real_file_via_sql_agent_registry(
    tmp_path: Path, database_url: str
) -> None:
    """No live provider credentials needed at all — see this module's
    own docstring. A real WorkflowStep, resolved through the real
    SqlAgentRegistry, genuinely executes a real file inside the
    sandbox and reports the real, correct outcome — proven for both a
    passing and a failing case, called directly (this agent's contract
    reads its structured input straight from `inputs`, the same direct
    path its own unit tests already exercise through AgentStepExecutor
    with a Context Manager; this integration test's own job is proving
    SqlAgentRegistry resolution feeds a working instance into that same
    dispatch, not re-proving the Context Manager bridge itself)."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

        (tmp_path / "ok.py").write_text("print('integration pass')\n", encoding="utf-8")
        (tmp_path / "broken.py").write_text("raise SystemExit(3)\n", encoding="utf-8")

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)
            assert isinstance(resolved, TestAgentEntrypoint)
            # Derived from the agent's own *actually-resolved* sandbox,
            # not a hardcoded `sys.executable` — `resolved` was
            # constructed by `EntrypointLoader`'s own zero-argument
            # `cls()` call, so its `sandbox` is whichever backend
            # `AIOS_SANDBOX_BACKEND` currently names (real `DockerSandbox`
            # by default), never necessarily this host's own interpreter
            # path. See `pipeline.py`'s own docstring for the identical
            # bug this mirrors and fixes.
            python_command = list(resolved.sandbox.python_command)

            passing = await resolved.execute(
                {
                    "workingDirectory": str(tmp_path),
                    "filePath": "ok.py",
                    "runCommand": [*python_command, "ok.py"],
                }
            )
            failing = await resolved.execute(
                {
                    "workingDirectory": str(tmp_path),
                    "filePath": "broken.py",
                    "runCommand": [*python_command, "broken.py"],
                }
            )

            TestAgentOutput.model_validate(passing)
            TestAgentOutput.model_validate(failing)
            assert passing["passed"] is True
            assert passing["exitCode"] == 0
            assert failing["passed"] is False
            assert failing["exitCode"] == 3
        finally:
            await engine.dispose()

    asyncio.run(_run())
