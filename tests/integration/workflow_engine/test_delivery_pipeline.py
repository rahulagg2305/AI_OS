"""The first genuine, end-to-end proof of a real, declared multi-step
Workflow Engine pipeline: Architecture -> Build -> Test -> Documentation,
chained through
`ai_os_kernel.context_manager.resolvers.WorkflowStepOutputResolver`
(built this step) and `tests.integration._delivery_pipeline`'s own
pipeline-specific configuration of it (relocated here from
`ai_os_pack_software_engineering.pipeline`, `platform_sdk_v1_scope.md`
step 7 — see that module's own docstring for why).

**Both tiers below need a real Postgres container — a genuine,
discovered fact about this specific test, not a limitation of its own
design.** Every prior single-agent test in this pack could stay
deterministic without one (`InMemoryAgentRegistry`, no persistence at
all — `AgentStepExecutor.execute()` called directly). This test's own
job is to prove a step's *real, persisted* output
(`workflow_steps.outputs`, data_model.md §4.3) genuinely reaches the
next step's real input — that hand-off only exists once
`WorkflowInstanceService`/`SqlWorkflowInstanceRepository` have actually
written it, so there is no way to prove it without the real,
Postgres-backed instance/step machinery underneath. The two tiers below
therefore differ only in whether the *agents themselves* make a real
LLM call — the identical Echo-vs-live split every other test in this
pack's own history already uses, just applied to all three prompted
agents in the same run instead of one at a time.

1. **Deterministic** — `InMemoryAgentRegistry`, all four real pack
   agents, `EchoLLMGateway`-backed completion services for the three
   `PromptedAgent`-backed ones. No pack registration/activation/seeding
   needed at all: `WorkflowInstanceService.create_instance()`'s own
   `pack_id` parameter is a plain, unenforced string column (no FK to
   `catalog.packs` exists — data_model.md §5, confirmed by inspection),
   and `InMemoryAgentRegistry` needs no catalog row to resolve an agent.
   **`sandbox=LocalSubprocessSandbox()` is passed explicitly to
   Build/Test/Documentation (2026-07-28)** — each agent's own bare
   default is now config-driven and defaults to `DockerSandbox`; this
   tier deliberately opts back into the fast, Docker-independent
   backend, since proving the four-step hand-off needs a real Postgres
   container already and gains nothing from also requiring Docker.
   `build_pipeline_trigger`'s own `python_command` is passed to match
   (a real, discovered bug once left these two independently resolved —
   see `_delivery_pipeline.py`'s own docstring). The
   real, Docker-gated proof of this same pipeline running through
   `DockerSandbox` lives in
   `tests/integration/sandbox/test_delivery_pipeline_docker.py`.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`)
   — the real `SqlAgentRegistry`, resolving all four real pack agents
   from real, seeded `catalog.agents` rows, using this pack's own three
   *real, shipped* prompts (`architecture_proposal.md`/
   `build_write_file.md`/`documentation_record_artifact.md`) rather
   than test-only substitutes — a genuine, positive difference from
   every prior single-agent live test in this pack's own history
   (`test_architecture_agent_pack.py`/`test_build_agent_pack.py` both
   needed a substitute prompt specifically because their own `{{context}}`
   placeholder needed a real Context Manager/workflow-instance round
   trip no single-agent test stood up — this test finally *is* that
   round trip, for real, end to end). This tier resolves each agent via
   `EntrypointLoader`'s own zero-argument `cls()` call, so it now
   exercises the real, config-driven `DockerSandbox` default too, on top
   of the real LLM call.
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
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, SqlAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.documentation import DocumentationAgentEntrypoint
from ai_os_pack_software_engineering.agents.verification import TestAgentEntrypoint
from tests.integration._delivery_pipeline import build_pipeline_trigger
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PACK_ROOT = REPO_ROOT / "capability_packs" / "software-engineering"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"

_AGENT_IDS = {
    "architecture": f"{_PACK_ID}/architecture",
    "build": f"{_PACK_ID}/build",
    "test": f"{_PACK_ID}/qa-test",
    "documentation": f"{_PACK_ID}/documentation",
}
_AGENT_ENTRYPOINTS = {
    "architecture": (
        "ai_os_pack_software_engineering.agents.architecture:ArchitectureAgentEntrypoint"
    ),
    "build": "ai_os_pack_software_engineering.agents.build:BuildAgentEntrypoint",
    "test": "ai_os_pack_software_engineering.agents.verification:TestAgentEntrypoint",
    "documentation": (
        "ai_os_pack_software_engineering.agents.documentation:DocumentationAgentEntrypoint"
    ),
}


def _test_agent_with_sandbox(sandbox: LocalSubprocessSandbox) -> TestAgentEntrypoint:
    """qa-test is migrated onto the Platform SDK (step 9) — no more
    ``sandbox=`` constructor override. Construct zero-arg, exactly as
    ``EntrypointLoader`` does, then bind the real ``PackContext`` a real
    caller would inject, granting exactly ``sandbox:execute``."""
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


async def _deterministic_service(template: str, prompt_id: str) -> PromptedCompletionService:
    return PromptedCompletionService(
        prompt_engine=InMemoryPromptEngine({(prompt_id, "0.1.0"): template}),
        llm_gateway=EchoLLMGateway(),
    )


@pytest.mark.asyncio
async def test_all_four_steps_genuinely_chain_through_real_persisted_outputs(
    tmp_path: Path, database_url: str
) -> None:
    """The real end-to-end proof this step exists for: a real, declared
    four-step WorkflowDefinition, driven to completion, in which each
    step's genuine output is proven — by inspecting the final artifact,
    not by a test hand-copying anything — to have reached the next
    step's genuine input."""

    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"

    async def build_service() -> PromptedCompletionService:
        # {{context}} (Architecture's own real, JSON-quoted output) is
        # deliberately placed in a comment-like prefix *before* the
        # FILE_PATH marker, never inside the generated file's own
        # Python string literal — `_parse_build_instruction` finds the
        # FILE_PATH/...END block anywhere in the completion, so this
        # proves the real hand-off (readable back from `instruction`)
        # without making the *written file's* own validity depend on
        # what upstream free text happens to contain (quotes, newlines).
        return await _deterministic_service(
            "Upstream design: {{context}}\n\n"
            "FILE_PATH: solution.py\n"
            "FILE_CONTENT_BEGIN\n"
            'print("hello from the pipeline")\n'
            "FILE_CONTENT_END",
            "build.write_file",
        )

    async def architecture_service() -> PromptedCompletionService:
        return await _deterministic_service(architecture_template, "architecture.propose_design")

    async def documentation_service() -> PromptedCompletionService:
        return await _deterministic_service(
            "# {{filePath}}\n\n"
            "Instruction: {{instruction}}\n"
            "Passed: {{passed}} (exit {{exitCode}})\n"
            "Output: {{output}}",
            "documentation.record_artifact",
        )

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["architecture"]: ArchitectureAgentEntrypoint(
                service_factory=architecture_service
            ),
            _AGENT_IDS["build"]: BuildAgentEntrypoint(
                service_factory=build_service,
                working_directory=tmp_path,
                sandbox=LocalSubprocessSandbox(),
            ),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: DocumentationAgentEntrypoint(
                service_factory=documentation_service, sandbox=LocalSubprocessSandbox()
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        # Matches the explicit `sandbox=LocalSubprocessSandbox()` given
        # to every agent above — see `_delivery_pipeline.py`'s own docstring for
        # why this must be passed explicitly rather than left to its
        # own default whenever a caller overrides an agent's sandbox.
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.COMPLETED
        assert result.error is None
        assert result.last_instance is not None

        written_file = tmp_path / "solution.py"
        assert written_file.is_file()
        assert (
            written_file.read_text(encoding="utf-8").strip() == 'print("hello from the pipeline")'
        )

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)
        build_outputs = next(s.outputs for s in steps if s.step_name == "build")
        assert build_outputs is not None
        # Architecture's own real output genuinely reached Build's own
        # real prompt — not hand-copied, read back from Build's own
        # persisted `instruction` field (its raw completion text).
        assert "DESIGN: a single Python script" in build_outputs["instruction"]
        assert "print a friendly message" in build_outputs["instruction"]  # via {{context}}

        doc_file = tmp_path / "solution.py.md"
        assert doc_file.is_file()
        doc_text = doc_file.read_text(encoding="utf-8")
        # Documentation's own real record genuinely reflects Test's own
        # real, correct outcome (exit 0 — the generated script always
        # succeeds) — not asserted from this test's own knowledge of
        # what "should" have happened.
        assert "solution.py" in doc_text
        assert "Passed: true" in doc_text
        assert "exit 0" in doc_text
    finally:
        await engine.dispose()


async def _register_and_activate_pack(database_url: str) -> None:
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
                reason="delivery pipeline integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_rows(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            for key, agent_id in _AGENT_IDS.items():
                permissions = (
                    '["sandbox:execute"]' if key == "test" else '["llm:invoke", "sandbox:execute"]'
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.agents "
                        "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                        " required_permissions, required_tools) "
                        "VALUES (:agent_id, :pack_id, :version, :entrypoint, "
                        " '{}'::jsonb, '{}'::jsonb, (:permissions)::jsonb, '[]'::jsonb) "
                        "ON CONFLICT (agent_id) DO NOTHING"
                    ),
                    {
                        "agent_id": agent_id,
                        "pack_id": _PACK_ID,
                        "version": _PACK_VERSION,
                        "entrypoint": _AGENT_ENTRYPOINTS[key],
                        "permissions": permissions,
                    },
                )
    finally:
        await engine.dispose()


async def _seed_real_prompts(database_url: str) -> None:
    """Seeds this pack's own three *real, shipped* prompts — see this
    module's own docstring for why this test, unlike every prior
    single-agent live test in this pack, can use them directly."""
    prompts = {
        "architecture.propose_design": PACK_ROOT / "prompts" / "architecture_proposal.md",
        "build.write_file": PACK_ROOT / "prompts" / "build_write_file.md",
        "documentation.record_artifact": PACK_ROOT / "prompts" / "documentation_record_artifact.md",
    }
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            for prompt_id, path in prompts.items():
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.prompts "
                        "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                        "VALUES "
                        "(:prompt_id, :pack_id, '0.1.0', :content, '{}'::jsonb, 'sha256:abc') "
                        "ON CONFLICT (prompt_id, version) DO NOTHING"
                    ),
                    {
                        "prompt_id": prompt_id,
                        "pack_id": _PACK_ID,
                        "content": path.read_text(encoding="utf-8"),
                    },
                )
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)
def test_the_real_pipeline_genuinely_runs_end_to_end_against_the_live_api(
    database_url: str,
) -> None:
    """Opt-in live: the full chain this step exists to prove, against
    the real Anthropic API and this pack's own real, shipped prompts —
    a real Documentation artifact, genuinely written to disk, at the
    end of a real, four-step run."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_rows(database_url)
        await _seed_real_prompts(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            trigger = build_pipeline_trigger(engine, registry)

            requirement = "Write a Python script that prints exactly: hello from the pipeline"
            result = await trigger(
                {"requirement": requirement},
                "test-principal",
            )

            assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error
            assert result.last_instance is not None

            steps = await SqlWorkflowInstanceRepository(engine).list_steps(
                result.last_instance.workflow_id
            )
            build_step = next(s for s in steps if s.step_name == "build")
            documentation_step = next(s for s in steps if s.step_name == "documentation")
            assert build_step.outputs is not None
            assert documentation_step.outputs is not None

            working_directory = Path(build_step.outputs["workingDirectory"])
            documentation_path = working_directory / documentation_step.outputs["documentationPath"]
            assert documentation_path.is_file()
            assert documentation_path.read_text(encoding="utf-8").strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
