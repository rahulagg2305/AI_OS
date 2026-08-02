"""Real, genuine proof that ``se.delivery_pipeline``'s new
``route-after-build`` decision step (``P02-S01-M05-T15``) genuinely
affects real pipeline behavior, against a real Postgres container
(ADR-0015 — no mocking the database) — the last of the four
``P02-S01-M05-T09``–``T12`` "proven, unused" capabilities to reach a
real, running pipeline.

Two real, opposite outcomes from the identical pipeline definition,
differing only in Build's own real, persisted ``written`` field:

1. **``written: true``** (the existing, unchanged path) — the real
   ``BuildAgentEntrypoint`` genuinely writes a real file;
   ``route-after-build`` genuinely persists ``{"outcome": true,
   "branch": "lint"}``; ``lint``/``quality-gate-lint-clean`` genuinely
   run and pass, exactly as before this step existed; the pipeline
   completes end to end through ``documentation``.
2. **``written: false``** — a small, directly-constructed fake Build
   agent (this test's own scope is `route-after-build`'s real
   branching, not re-exercising Build's own already-proven sandbox
   mechanics — ``test_build_agent_pack.py``'s own job) returns a
   schema-valid output with ``written: false`` and a ``filePath`` that
   is genuinely never written to disk. ``route-after-build`` genuinely
   persists ``{"outcome": false, "branch": "test"}``. The test registry
   deliberately omits ``lint``/``documentation`` entirely — if the
   decision ever wrongly routed to ``lint``, the run would fail loudly
   with a clear ``AgentNotRegisteredError``, not silently pass. `test`
   genuinely runs directly (skipping `lint`/`quality-gate-lint-clean`
   entirely — no `workflow_steps` row for either), and genuinely fails
   against the real, correctly-missing file (`TestInstructionError`,
   `qa-test`'s own already-shipped contract) — a real, different
   failure mode than the existing `quality-gate-tests-pass` gate halt,
   proven never to reach `documentation`.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
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
from ai_os_pack_software_engineering.agents.verification import (
    TestAgentEntrypoint,
    TestInstructionError,
)
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


def _unconfigured_git_push_agent() -> GitPushAgentEntrypoint:
    """``se.delivery_pipeline``'s new, final step (``P03-S04-M31-T04``)
    — a bare, zero-arg ``GitPushAgentEntrypoint()`` (``remote_url=
    None``) is a real, structured no-op, preserving this file's own
    existing assertions unchanged. See
    ``test_delivery_pipeline.py``'s own identical helper."""
    return GitPushAgentEntrypoint()


_BUILD_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workingDirectory": {"type": "string"},
        "filePath": {"type": "string"},
        "written": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "instruction": {"type": "string"},
    },
    "required": [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
    ],
    "additionalProperties": False,
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
    template: str, prompt_id: str, *, working_directory: Path
) -> BuildAgentEntrypoint:
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=LocalSubprocessSandbox(),
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


def _documentation_agent_with_prompt(template: str, prompt_id: str) -> DocumentationAgentEntrypoint:
    agent = DocumentationAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


class _FakeBuildAgentWithFailedWrite:
    """A minimal, directly-constructed ``Agent`` — not the real
    ``BuildAgentEntrypoint`` — returning a schema-valid output with
    ``written: false`` and a ``filePath`` that is genuinely never
    written to disk, so `qa-test`'s own later, real execution genuinely
    fails against a real missing file, not a simulated failure."""

    output_schema: dict[str, Any] = _BUILD_OUTPUT_SCHEMA

    def __init__(self, *, working_directory: Path, file_path: str) -> None:
        self._working_directory = working_directory
        self._file_path = file_path

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "workingDirectory": str(self._working_directory),
            "filePath": self._file_path,
            "written": False,
            "exitCode": 1,
            "stdout": "",
            "stderr": "simulated write failure for route-after-build's own test",
            "instruction": (
                f"FILE_PATH: {self._file_path}\nFILE_CONTENT_BEGIN\nprint(1)\nFILE_CONTENT_END"
            ),
        }


def test_a_successful_build_write_takes_the_true_branch_through_lint_unchanged(
    tmp_path: Path, database_url: str
) -> None:
    requirements_analyst_template = "ANALYSIS: refined.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a script.\nContext was: {{context}}"
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        'print("hello from route-after-build")\n'
        "FILE_CONTENT_END"
    )
    documentation_template = "# {{filePath}}\nPassed: {{passed}} (exit {{exitCode}})"

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                requirements_analyst_template, "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                architecture_template, "architecture.propose_design"
            ),
            _AGENT_IDS["build"]: _build_agent_with_prompt(
                build_template, "build.write_file", working_directory=tmp_path
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
            _AGENT_IDS["git-push"]: _unconfigured_git_push_agent(),
        }
    )

    engine: AsyncEngine = build_engine(database_url)

    async def _run() -> None:
        try:
            trigger = build_pipeline_trigger(
                engine, registry, python_command=LocalSubprocessSandbox().python_command
            )

            result = await trigger({"requirement": "print a friendly message"}, "test-principal")

            # A real approve-git-push human_approval point
            # (P03-S03-M30-T05) now sits between documentation and
            # git-push — every assertion below reads a step that already
            # ran and persisted its output before that point, so a
            # genuine pause here is the correct outcome.
            assert result.outcome == WorkflowRunOutcome.WAITING_FOR_HUMAN
            assert result.error is None
            assert result.last_instance is not None

            repository = SqlWorkflowInstanceRepository(engine)
            steps = await repository.list_steps(result.last_instance.workflow_id)

            decision_outputs = next(s.outputs for s in steps if s.step_name == "route-after-build")
            assert decision_outputs == {"outcome": True, "branch": "lint"}

            lint_outputs = next(s.outputs for s in steps if s.step_name == "lint")
            assert lint_outputs is not None
            assert lint_outputs["passed"] is True

            lint_gate_outputs = next(
                s.outputs for s in steps if s.step_name == "quality-gate-lint-clean"
            )
            assert lint_gate_outputs is not None
            assert lint_gate_outputs["passed"] is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_build_write_takes_the_false_branch_and_skips_lint_entirely(
    tmp_path: Path, database_url: str
) -> None:
    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                "ANALYSIS: refined.\nRaw ask was: {{context}}", "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                "DESIGN: a script.\nContext was: {{context}}", "architecture.propose_design"
            ),
            _AGENT_IDS["build"]: _FakeBuildAgentWithFailedWrite(
                working_directory=tmp_path, file_path="never_written.py"
            ),
            # Deliberately no "lint" or "documentation" entries: if
            # route-after-build ever wrongly took the "true" branch, or
            # the pipeline somehow still reached documentation, this
            # run would fail loudly with AgentNotRegisteredError — not
            # silently pass.
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
        }
    )

    engine: AsyncEngine = build_engine(database_url)

    async def _run() -> None:
        try:
            trigger = build_pipeline_trigger(
                engine, registry, python_command=LocalSubprocessSandbox().python_command
            )

            result = await trigger({"requirement": "print a friendly message"}, "test-principal")

            assert result.outcome == WorkflowRunOutcome.FAILED
            assert isinstance(result.error, TestInstructionError)
            assert result.last_instance is not None

            repository = SqlWorkflowInstanceRepository(engine)
            steps = await repository.list_steps(result.last_instance.workflow_id)
            step_names = {s.step_name for s in steps}

            decision_outputs = next(s.outputs for s in steps if s.step_name == "route-after-build")
            assert decision_outputs == {"outcome": False, "branch": "test"}

            # The real proof: lint (and its own gate) were genuinely
            # never invoked at all — no workflow_steps row for either.
            assert "lint" not in step_names
            assert "quality-gate-lint-clean" not in step_names

            # test genuinely ran (and genuinely failed, recorded as a
            # real failed attempt) directly after the decision step.
            test_step = next(s for s in steps if s.step_name == "test")
            assert test_step.status == "failed"
            assert test_step.error is not None

            # documentation never ran — the pipeline halted first.
            assert "documentation" not in step_names
            assert not (tmp_path / "never_written.py.md").exists()
        finally:
            await engine.dispose()

    asyncio.run(_run())
