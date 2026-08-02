"""The real, end-to-end proof this step exists for
(``P03-S04-M31-T04``): a genuine ``se.delivery_pipeline`` run — all
seven real agents, through the real Workflow Engine, against a real
Postgres container (ADR-0015 — no mocking the database) — genuinely
commits and pushes Build's own real, generated file through the full
stack: agent -> ``ToolInvokerAdapter`` -> ``GitIntegrationService`` ->
a real ``LocalSubprocessSandbox`` -> a real ``git`` subprocess -> a
real, separate bare repository, verified by reading that repository's
own refs directly, never by trusting this pipeline's own return value
alone — the identical rigor
``tests/integration/git_integration/test_git_integration_service.py``
and ``tests/unit/kernel/sdk_adapters/test_tool_invoker_adapter.py``
already established for the two layers below this one.

This is a genuinely different proof than either of those: they exercise
``GitIntegrationService``/``ToolInvokerAdapter`` directly. This file
proves a real *workflow* — the same declared
``se.delivery_pipeline.yaml`` the real HTTP route drives — reaches all
the way down to a real git push, through the real agent dispatch chain,
not a shortcut that skips the Workflow Engine or the pack's own agent
code.

Deliberately not a modification of ``test_delivery_pipeline.py``'s own
extensive existing tests — those prove the six-agent chain and both
quality gates in detail and now register ``git-push`` unconfigured (a
real, structured no-op) to stay unchanged; this is the one, focused,
real-git-configured counterpart, mirroring
``test_delivery_pipeline_decision_routing.py``'s own precedent of a
dedicated file for one new step's own real behaviour.
"""

import asyncio
import os
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.git_integration.models import GitPushPolicy
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.observability.audit import AuditOutcome, SqlAuditLogWriter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.delivery_pipeline import build_pipeline_trigger
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
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

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

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


def _git_push_agent_with_real_service(
    *, sandbox: LocalSubprocessSandbox, git_service: GitIntegrationService, remote_url: str
) -> GitPushAgentEntrypoint:
    """The one real, configured case this file exists for: a real
    ``remote_url`` and a real, injected ``GitIntegrationService`` —
    genuinely commits and pushes, unlike every other test in this pack,
    which registers this agent unconfigured (a real, structured
    no-op)."""
    agent = GitPushAgentEntrypoint(remote_url=remote_url)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=sandbox,
            git_service=git_service,
        )
    )
    return agent


def test_a_real_pipeline_run_genuinely_commits_and_pushes_through_the_full_stack(
    tmp_path: Path, database_url: str
) -> None:
    """The real proof: Requirements Analyst -> Architecture -> Build ->
    Lint -> Test -> Documentation -> Git Push, all seven real agents,
    through the real, declared ``se.delivery_pipeline.yaml`` — ending in
    a real commit and a real push to a real, separate bare repository,
    verified by reading that repository's own refs directly."""

    async def _run() -> None:
        workspace = tmp_path / "workspace"
        remote = tmp_path / "remote.git"
        workspace.mkdir()
        await _git(["init", "--bare", str(remote)])

        engine: AsyncEngine = build_engine(database_url)
        try:
            sandbox = LocalSubprocessSandbox()
            audit_log = SqlAuditLogWriter(engine)
            git_service = GitIntegrationService(
                sandbox=sandbox,
                audit_log=audit_log,
                push_policy=GitPushPolicy(protected_branches=frozenset()),
                author_name="AI_OS Delivery Pipeline",
                author_email="delivery-pipeline@ai-os.internal",
            )

            requirements_analyst_template = (
                "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
            )
            architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
            build_template = (
                "Upstream design: {{context}}\n\n"
                "FILE_PATH: solution.py\n"
                "FILE_CONTENT_BEGIN\n"
                'print("hello from the real pipeline push")\n'
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
                        build_template,
                        "build.write_file",
                        working_directory=workspace,
                        sandbox=sandbox,
                    ),
                    _AGENT_IDS["lint"]: _lint_agent_with_sandbox(sandbox),
                    _AGENT_IDS["test"]: _test_agent_with_sandbox(sandbox),
                    _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                        documentation_template, "documentation.record_artifact", sandbox=sandbox
                    ),
                    _AGENT_IDS["git-push"]: _git_push_agent_with_real_service(
                        sandbox=sandbox, git_service=git_service, remote_url=str(remote)
                    ),
                }
            )

            trigger = build_pipeline_trigger(
                engine, registry, python_command=sandbox.python_command
            )

            result = await trigger({"requirement": "print a friendly message"}, "test-principal")

            assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error
            assert result.last_instance is not None

            repository = SqlWorkflowInstanceRepository(engine)
            steps = await repository.list_steps(result.last_instance.workflow_id)

            git_push_outputs = next(s.outputs for s in steps if s.step_name == "git-push")
            assert git_push_outputs is not None
            assert git_push_outputs["pushed"] is True
            assert git_push_outputs["reason"] is None
            commit_sha = git_push_outputs["commitSha"]
            branch = git_push_outputs["branch"]
            assert commit_sha
            assert branch

            # The real, separate remote genuinely received it — read
            # directly, not through this pipeline's own return value.
            refs = await _git(["ls-remote", str(remote)])
            assert commit_sha in refs.stdout
            assert f"refs/heads/{branch}" in refs.stdout

            # The real commit genuinely contains Build's own real file.
            show = await _git(["show", f"{commit_sha}:solution.py"], cwd=workspace)
            assert show.stdout.strip() == 'print("hello from the real pipeline push")'

            # Real, hash-chained audit rows for both real git operations.
            audit_rows = await audit_log.list_all()
            commit_row = next(r for r in audit_rows if r.event_type == "git.commit.succeeded")
            assert commit_row.outcome == AuditOutcome.SUCCESS
            assert commit_row.detail["commit_sha"] == commit_sha
            push_row = next(r for r in audit_rows if r.event_type == "git.push.succeeded")
            assert push_row.outcome == AuditOutcome.SUCCESS
            assert push_row.detail["branch"] == branch
        finally:
            await engine.dispose()

    asyncio.run(_run())
