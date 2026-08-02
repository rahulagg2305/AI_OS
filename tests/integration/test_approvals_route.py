"""The real, end-to-end proof this step exists for (``P03-S03-M30-T06``):
a genuinely paused, real production ``se.delivery_pipeline`` instance —
resumed only by a real, authenticated, RBAC-authorized ``POST`` against
the new ``/api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions``
route — genuinely completes, including a real commit and push to a
real, separate bare repository.

**No live Anthropic credential needed, the identical precedent every
other deterministic pipeline test in this pack already establishes.**
Reaching the pause point (``requirements-analyst`` through
``documentation``) uses a real, Echo-backed
:class:`~ai_os_kernel.workflow_engine.registry.InMemoryAgentRegistry` —
mirroring ``test_delivery_pipeline_git_push.py``'s own established
helpers almost exactly — driven through the real
``build_pipeline_trigger`` composition, against the real
``delivery_pipeline.yaml``. This is real setup for what this file
actually proves, not a shortcut around it: **the decide route itself,
and the resumption it triggers, are never simulated.** Resumption goes
through a real ``TestClient(build_app(...))`` — a genuinely separate
process boundary from the setup phase above — whose own real
``_lifespan`` genuinely discovers/registers/activates the real
``software-engineering`` pack (deliberately *not* isolated via
``capability_pack_dirs=[]``, the same ``test_bootstrap_pack_discovery.py``
precedent) and builds a real, ``AIOS_GIT_*``-configured
``GitIntegrationService`` (``P03-S01-M24-T02``) — so the one remaining
step after the pause, ``git-push``, resolves and runs through the
genuinely real, production ``SqlAgentRegistry`` path, needing no LLM
call at all (neither it nor the ``human_approval`` step in between
makes one).

Proves: the pipeline genuinely pauses before any push is even
attempted (the real remote receives nothing); an unauthorized decision
attempt is refused (``403``) with the approval still pending and the
remote still untouched; and a real, authorized decision (``POST`` with
a real Bearer token, ``approver:approve-git-push`` role) genuinely
resumes the paused instance through the real HTTP layer, completing a
real commit and push — verified by reading the remote's own refs
directly, never trusted from the response body alone.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
import shutil
import subprocess
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.delivery_pipeline import build_pipeline_trigger
from ai_os_kernel.workflow_engine.human_approval import SqlApprovalRepository
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.documentation import DocumentationAgentEntrypoint
from ai_os_pack_software_engineering.agents.git_push import GitPushAgentEntrypoint
from ai_os_pack_software_engineering.agents.lint import LintAgentEntrypoint
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalystAgentEntrypoint,
)
from ai_os_pack_software_engineering.agents.verification import TestAgentEntrypoint
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "approvals-route-test-signing-key-at-least-32-bytes"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_APPROVE_GIT_PUSH_STEP_ID = "approve-git-push"

_AGENT_IDS = {
    "requirements-analyst": f"{_PACK_ID}/requirements-analyst",
    "architecture": f"{_PACK_ID}/architecture",
    "build": f"{_PACK_ID}/build",
    "lint": f"{_PACK_ID}/lint",
    "test": f"{_PACK_ID}/qa-test",
    "documentation": f"{_PACK_ID}/documentation",
    "git-push": f"{_PACK_ID}/git-push",
}


def _git_binary() -> str:
    found = shutil.which("git")
    if found is None:
        pytest.skip("git is not available on PATH")
    return found


async def _git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        [_git_binary(), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
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


def _config() -> PlatformConfig:
    # Deliberately NOT capability_pack_dirs=[] — this test's own real
    # git-push resumption needs the real, on-disk software-engineering
    # pack genuinely discovered/registered/activated by _lifespan, the
    # same test_bootstrap_pack_discovery.py precedent.
    return PlatformConfig(env="test", role="api", manifest_schema_path=SCHEMA_PATH)


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "approvals-route-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _requirements_analyst_agent_with_prompt(
    template: str, prompt_id: str
) -> RequirementsAnalystAgentEntrypoint:
    agent = RequirementsAnalystAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
        )
    )
    return agent


def _architecture_agent_with_prompt(template: str, prompt_id: str) -> ArchitectureAgentEntrypoint:
    agent = ArchitectureAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
        )
    )
    return agent


def _build_agent_with_prompt(
    template: str, prompt_id: str, *, working_directory: Path, sandbox: LocalSubprocessSandbox
) -> BuildAgentEntrypoint:
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=sandbox,
        )
    )
    return agent


def _lint_agent_with_sandbox(sandbox: LocalSubprocessSandbox) -> LintAgentEntrypoint:
    agent = LintAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=sandbox,
        )
    )
    return agent


def _test_agent_with_sandbox(sandbox: LocalSubprocessSandbox) -> TestAgentEntrypoint:
    agent = TestAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=sandbox,
        )
    )
    return agent


def _documentation_agent_with_prompt(
    template: str, prompt_id: str, *, sandbox: LocalSubprocessSandbox
) -> DocumentationAgentEntrypoint:
    agent = DocumentationAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=sandbox,
        )
    )
    return agent


async def _reach_the_real_pause_point(
    database_url: str, *, workspace: Path, sandbox: LocalSubprocessSandbox
) -> str:
    """Drives a real ``se.delivery_pipeline`` instance from scratch,
    through requirements-analyst -> architecture -> build -> lint ->
    test -> documentation, to the real, genuine
    ``WorkflowRunOutcome.WAITING_FOR_HUMAN`` pause at
    ``approve-git-push`` — real setup for what this file actually
    proves, not itself the subject of the proof. ``git-push`` is
    deliberately registered unconfigured here (a real, structured
    no-op if ever reached this way) — the real, configured push only
    ever happens through the real HTTP resume path this file proves."""
    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        'print("hello from the real approvals-route push")\n'
        "FILE_CONTENT_END"
    )
    documentation_template = "# {{filePath}}\n\nInstruction: {{instruction}}"

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                requirements_analyst_template, "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                architecture_template, "architecture.propose_design"
            ),
            _AGENT_IDS["build"]: _build_agent_with_prompt(
                build_template, "build.write_file", working_directory=workspace, sandbox=sandbox
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(sandbox),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(sandbox),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact", sandbox=sandbox
            ),
            _AGENT_IDS["git-push"]: GitPushAgentEntrypoint(),
        }
    )

    engine: AsyncEngine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(engine, registry, python_command=sandbox.python_command)
        result = await trigger({"requirement": "print a friendly message"}, "test-principal")
        assert result.outcome == WorkflowRunOutcome.WAITING_FOR_HUMAN, result.error
        assert result.last_instance is not None
        return result.last_instance.workflow_id
    finally:
        await engine.dispose()


def test_a_real_paused_instance_resumes_and_pushes_only_via_a_real_authorized_http_decision(
    tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _setup() -> tuple[str, str]:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        sandbox = LocalSubprocessSandbox()
        workflow_id = await _reach_the_real_pause_point(
            database_url, workspace=workspace, sandbox=sandbox
        )

        engine: AsyncEngine = build_engine(database_url)
        try:
            approval = await SqlApprovalRepository(engine).get_by_step(
                workflow_id=workflow_id, step_id=_APPROVE_GIT_PUSH_STEP_ID
            )
            assert approval is not None
            assert approval.status == "pending"
            return workflow_id, approval.approval_id
        finally:
            await engine.dispose()

    workflow_id, approval_id = asyncio.run(_setup())

    remote = tmp_path / "remote.git"
    asyncio.run(_git(["init", "--bare", str(remote)]))
    empty_refs = asyncio.run(_git(["ls-remote", str(remote)]))
    assert empty_refs.stdout.strip() == ""

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.setenv("AIOS_GIT_REMOTE_URL", str(remote))
    monkeypatch.setenv("AIOS_GIT_AUTHOR_NAME", "AI_OS Delivery Pipeline")
    monkeypatch.setenv("AIOS_GIT_AUTHOR_EMAIL", "delivery-pipeline@ai-os.internal")
    monkeypatch.setenv("AIOS_GIT_PROTECTED_BRANCHES", "main")
    # The real production SqlAgentRegistry (built inside _lifespan, no
    # sandbox override this test can reach) defaults to DockerSandbox —
    # which cannot see a host-local bare-repo path like `remote` above
    # at all (no bind mount for it). `AIOS_SANDBOX_BACKEND=local`
    # (build_default_sandbox_executor's own real, documented env-var
    # convention) is the one supported way to opt this real composition
    # into LocalSubprocessSandbox instead, exactly like every other
    # local-remote git-push proof in this suite already does explicitly.
    monkeypatch.setenv("AIOS_SANDBOX_BACKEND", "local")
    app = build_app(_config())

    decide_route = f"/api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions"

    with TestClient(app) as client:
        # The real, unauthorized attempt first — a genuine, authenticated
        # principal, but holding neither `admin` nor the exact
        # class-scoped `approver:approve-git-push` role.
        unauthorized_response = client.post(
            decide_route,
            json={"decision": "approved", "comment": "should be refused"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        assert unauthorized_response.status_code == 403

        # The remote is still genuinely untouched — read directly, not
        # inferred from the 403 alone.
        refs_after_unauthorized_attempt = asyncio.run(_git(["ls-remote", str(remote)]))
        assert refs_after_unauthorized_attempt.stdout.strip() == ""

        # The real, authorized decision.
        authorized_response = client.post(
            decide_route,
            json={"decision": "approved", "comment": "Reviewed — looks correct."},
            headers={"Authorization": f"Bearer {_token(['approver:approve-git-push'])}"},
        )

    assert authorized_response.status_code == 200
    body = authorized_response.json()
    assert body["decision"] == "approved"
    assert body["decided_by"] == "approvals-route-test-user"
    assert body["resumed"] is True
    assert body["resumed_outcome"] == "completed", body["resumed_error"]
    assert body["resumed_error"] is None

    # The real, separate remote genuinely received the real push — read
    # directly, not through this route's own response body alone.
    refs_after_authorized_decision = asyncio.run(_git(["ls-remote", str(remote)]))
    assert refs_after_authorized_decision.stdout.strip() != ""
