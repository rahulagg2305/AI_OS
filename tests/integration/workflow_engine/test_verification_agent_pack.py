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

**A real, discovered gap from step 9's migration, resolved for real in
step 9a — no more test-side workaround.** Step 9 found that nothing in
`SqlAgentRegistry` ever called `bind_pack_context()` after resolving an
entrypoint, and this file's own tests (run unconditionally, no API-key
gate, since this agent makes no LLM call) were the first real,
unconditionally-run exercise of that gap — they used to bind a
`PackContext` by hand, standing in for production wiring. Step 9a closed
that gap for real, inside `SqlAgentRegistry.resolve_agent()` itself:
every resolved entrypoint that implements
`PackContextReceiver` is now genuinely injected a real, permission-gated
`PackContext` (built from *its own row's* `required_permissions`)
**before** `resolve_agent()` ever returns it. This file's own tests below
now do **no manual binding at all** — `resolved.execute(...)` working is
proof that production wiring did its job, not that the test compensated
for a gap that no longer exists.

**The `python_command` introspection question, revisited and resolved
the same way at this layer too.** Step 9 found that a migrated agent's
only sandbox access (the injected, opaque `ToolInvoker`) has no
`python_command` introspection, and worked around it by having the
*test* build and keep its own `SandboxExecutor` reference. Now that
`SqlAgentRegistry` itself builds the sandbox it injects,
`SqlAgentRegistry.__init__` accepts the identical `sandbox=` override
this step's own registry change adds — so this file passes its own
`SandboxExecutor` into the registry's constructor and keeps the same
reference for `python_command`, rather than trying to reintrospect
whatever the registry might have built internally. The
"caller already holds the one reference it needs" principle generalizes
cleanly one layer up; no new capability was needed anywhere.
"""

import asyncio
import contextlib
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_pack_software_engineering.agents.verification import (
    TestAgentEntrypoint,
    TestAgentOutput,
)
from ai_os_sdk.contracts import PackContextReceiver
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PACK_ROOT = REPO_ROOT / "capability_packs" / "software-engineering"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/qa-test"


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
    test_build_agent_pack.py's own helper exactly.

    **``pack_root=PACK_ROOT`` (added this step) genuinely derives and
    writes this pack's real ``catalog.agents``/``catalog.prompts``/
    ``catalog.tools`` rows** — see
    ``ai_os_kernel.capability_manager.manifest_catalog_installer``.
    Replaces the hand-written ``catalog.agents`` row a prior version of
    this file inserted via raw SQL (``_seed_agent_row``, removed)."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (PACK_ROOT / "manifest.yaml").open(encoding="utf-8") as fh:
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
                pack_root=PACK_ROOT,
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


def test_sql_agent_registry_genuinely_resolves_the_test_agent(database_url: str) -> None:
    """Deterministic. Proves the Test Agent is genuinely resolvable
    through SqlAgentRegistry — the same tension already closed for its
    two pack-mates."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, PackContextReceiver)
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
    dispatch, not re-proving the Context Manager bridge itself).

    **Step 9a's own real proof: no `bind_pack_context()` call anywhere
    in this test.** `SqlAgentRegistry.resolve_agent()` alone must leave
    `resolved` genuinely usable — the two real executions below succeed
    or fail purely on the real file's own exit code, exactly as before
    step 9's migration, proving production wiring does the job the test
    used to do by hand."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)

        (tmp_path / "ok.py").write_text("print('integration pass')\n", encoding="utf-8")
        (tmp_path / "broken.py").write_text("raise SystemExit(3)\n", encoding="utf-8")

        # Built once, here, by the caller, and handed to the registry's
        # own `sandbox=` override — the identical "the caller already
        # holds the one reference it needs" principle step 9 established
        # for `python_command` introspection, now applied one layer up:
        # this test needs to know which real backend was used, and
        # supplying it explicitly is simpler and more honest than trying
        # to reintrospect whatever the registry might have built for
        # itself by default. `AIOS_SANDBOX_BACKEND` still governs which
        # real backend `build_default_sandbox_executor()` resolves to
        # (DockerSandbox by default).
        sandbox = build_default_sandbox_executor()
        python_command = list(sandbox.python_command)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine, sandbox=sandbox)
            resolved = await registry.resolve_agent(_AGENT_ID)
            assert isinstance(resolved, TestAgentEntrypoint)
            assert isinstance(resolved, PackContextReceiver)

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
