"""The first genuine, end-to-end proof of a real, declared multi-step
Workflow Engine pipeline: Requirements Analyst -> Architecture -> Build
-> Test -> Documentation, chained through
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

1. **Deterministic** — `InMemoryAgentRegistry`, all five real pack
   agents, `EchoLLMGateway`-backed completion services for the four
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
   — the real `SqlAgentRegistry`, resolving all five real pack agents
   from real, seeded `catalog.agents` rows, using this pack's own four
   *real, shipped* prompts (`requirements_analysis.md`/
   `architecture_proposal.md`/`build_write_file.md`/
   `documentation_record_artifact.md`) rather than test-only substitutes
   — a genuine, positive difference from every prior single-agent live
   test in this pack's own history (`test_architecture_agent_pack.py`/
   `test_build_agent_pack.py` both needed a substitute prompt
   specifically because their own `{{context}}` placeholder needed a
   real Context Manager/workflow-instance round trip no single-agent
   test stood up — this test finally *is* that round trip, for real, end
   to end). This tier resolves each agent via `EntrypointLoader`'s own
   zero-argument `cls()` call, so it now exercises the real,
   config-driven `DockerSandbox` default too, on top of the real LLM
   call.

**All five agents this pipeline chains — qa-test (step 9), architecture
(step 11), build (step 12), documentation (step 13), and
requirements-analyst (step 10, wired into this pipeline as its own
first step in this feature step) — are migrated onto the Platform SDK.
This pipeline now exercises all 5 of this pack's built agents, not 4 of
5.** The deterministic tier's `InMemoryAgentRegistry` no longer
constructs any of the five with a `service_factory`/`sandbox=`
override; `_requirements_analyst_agent_with_prompt`/
`_architecture_agent_with_prompt`/`_test_agent_with_sandbox`/
`_build_agent_with_prompt`/`_documentation_agent_with_prompt` construct
each zero-arg (aside from build's own `working_directory`) and
`bind_pack_context()` it, mirroring the exact real caller sequence
`SqlAgentRegistry` itself performs (step 9a). The live tier's
`SqlAgentRegistry(engine)` call already supplies real
`llm_gateway`/`prompt_engine` objects (`_build_real_llm_gateway_and_prompt_engine`
below) — requirements-analyst's own declared `llm:invoke` permission
needs the identical backing pair the other three prompted migrations
already required, so no further change was needed there.

**Requirements Analyst's own real output now genuinely reaches
Architecture's real input — the one new hand-off this feature step
adds, proven the same way every other hand-off in this pipeline already
is: by reading it back from a later step's own real, persisted output,
never by hand-copying anything.** See `ai_os_kernel.workflow_engine.delivery_pipeline`'s
own docstring for the full `_STEP_SOURCES`/`_FIELD_SELECTORS` wiring —
`architecture`'s own `context` prompt variable now comes from
`requirements-analyst`'s output (field-selected to `analysis`), not the
workflow's own raw top-level `requirement` input directly any more.
"""

import asyncio
import contextlib
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import gate_results
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine, PromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.delivery_pipeline import build_pipeline_trigger
from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, SqlAgentRegistry
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
PACK_ROOT = REPO_ROOT / "capability_packs" / "software-engineering"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_CONFIG_PATH = REPO_ROOT / "config" / "llm.yaml"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential


async def _real_gate_results(
    engine: AsyncEngine, *, workflow_id: str, step_id: str
) -> list[Row[Any]]:
    """Reads back real, persisted ``evaluation.gate_results`` rows for
    one gate step, ordered by insertion — the general-step-retry step's
    own real proof that `WorkflowInstanceService`'s injected
    `SqlGateResultRecorder` (`build_pipeline_trigger`'s own composition)
    genuinely wrote them, not a re-derivation of what the pipeline
    itself already asserts via `workflow_steps`."""
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(gate_results)
            .where(gate_results.c.workflow_id == workflow_id, gate_results.c.step_id == step_id)
            .order_by(gate_results.c.result_id)
        )
        return list(result.all())


async def _build_real_llm_gateway_and_prompt_engine(
    engine: AsyncEngine,
) -> tuple[KernelLLMGatewayProtocol, PromptEngine]:
    """The identical real composition
    ``test_requirements_analyst_agent_pack.py`` already established for
    the live-tier `SqlAgentRegistry` a migrated, `llm:invoke`-declaring
    agent needs — required here because `architecture` (step 11) is now
    one of the four agents this live test resolves through the real
    registry, and step 9a's own injection logic genuinely requires a
    real backing pair the moment `resolve_agent()` sees that permission."""
    provider_config = load_provider_config(_CONFIG_PATH)
    router = StaticRouter(
        routes={
            alias: RoutingDecision(
                provider=provider_config.providers.get(alias, PROVIDER_NAME), model_id=model_id
            )
            for alias, model_id in provider_config.model_ids.items()
        }
    )
    anthropic_gateway = await build_anthropic_adapter(
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=router,
        pricing=provider_config.pricing,
    )
    llm_gateway = DispatchingLLMGateway(router=router, gateways={PROVIDER_NAME: anthropic_gateway})
    return llm_gateway, SqlPromptCatalog(engine)


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
    — every test in this file predates real git-push and is not testing
    it; a bare, zero-arg ``GitPushAgentEntrypoint()`` (``remote_url=
    None``) is a real, structured no-op (``pushed: false``), preserving
    every existing assertion in this file completely unchanged. The
    real, configured, end-to-end proof lives in
    ``test_delivery_pipeline_git_push.py``."""
    return GitPushAgentEntrypoint()


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


def _lint_agent_with_sandbox(sandbox: LocalSubprocessSandbox) -> LintAgentEntrypoint:
    """The Lint Agent (added 2026-07-30) — genuinely SDK-native from the
    start, no migration needed. Construct zero-arg, exactly as
    ``EntrypointLoader`` does, then bind the real ``PackContext`` a real
    caller would inject, granting exactly ``sandbox:execute`` — the
    identical pattern ``_test_agent_with_sandbox`` already establishes."""
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


def _requirements_analyst_agent_with_prompt(
    template: str, prompt_id: str
) -> RequirementsAnalystAgentEntrypoint:
    """requirements-analyst is migrated onto the Platform SDK (step 10)
    — no `service_factory` constructor override. Construct zero-arg,
    exactly as `EntrypointLoader` does, then bind the real `PackContext`
    a real caller would inject, granting exactly `llm:invoke` over a
    real, Echo-backed gateway and an in-memory prompt engine seeded with
    `template` — the identical pattern `_architecture_agent_with_prompt`
    already established, now this pipeline's own first step."""
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
    """architecture is migrated onto the Platform SDK (step 11) — no
    more ``service_factory`` constructor override. Construct zero-arg,
    exactly as ``EntrypointLoader`` does, then bind the real
    ``PackContext`` a real caller would inject, granting exactly
    ``llm:invoke`` over a real, Echo-backed gateway and an in-memory
    prompt engine seeded with ``template`` — the identical pattern
    ``_test_agent_with_sandbox`` already established for ``qa-test``."""
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
    """build is migrated onto the Platform SDK (step 12) — no more
    ``service_factory``/``sandbox`` constructor overrides. Construct
    zero-arg (aside from ``working_directory``, still a legitimate
    override — see the agent's own module docstring), then bind the
    real ``PackContext`` a real caller would inject, granting both
    ``llm:invoke`` and ``sandbox:execute`` — the first agent in this
    pipeline needing both together. No ``python_command`` to supply any
    more (step 12a) — ``ToolInvokerAdapter`` resolves the real,
    portable interpreter invocation itself, from the same
    ``LocalSubprocessSandbox`` instance passed to ``build_pack_context``
    below, automatically."""
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


class _FlakyLLMGateway:
    """Wraps a real `LLMGateway` (`EchoLLMGateway` below), raising a
    real `LLMProviderError` on its own first `failures_before_success`
    calls before delegating to the wrapped gateway for real — the
    identical "genuine, controllable transient condition, not a coin
    flip" shape `test_a_gate_failure_within_the_retry_bound_eventually_succeeds`
    already establishes via a marker file on disk, applied at the LLM
    Gateway boundary instead, to prove a non-gate step (`build`) itself
    now genuinely retries too (general, error-category-driven step
    retry, added 2026-07-30). `retriable` (default `True`, matching
    `LLMProviderError`'s own documented default) lets the same fixture
    also produce the *non*-retriable proof: a real, explicit
    `retriable=False` classification (llm_gateway.md §10's own
    `permanent`/`budget` rows) that must never retry, even with a real,
    configured `_STEP_RETRY_TARGETS` entry for the step raising it."""

    def __init__(
        self,
        delegate: KernelLLMGatewayProtocol,
        *,
        failures_before_success: int,
        retriable: bool = True,
    ) -> None:
        self._delegate = delegate
        self._failures_before_success = failures_before_success
        self._retriable = retriable
        self.attempts = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.attempts += 1
        if self.attempts <= self._failures_before_success:
            raise LLMProviderError("simulated provider failure", retriable=self._retriable)
        return await self._delegate.complete(request)


def _build_agent_with_flaky_llm_gateway(
    template: str,
    prompt_id: str,
    *,
    working_directory: Path,
    llm_gateway: KernelLLMGatewayProtocol,
) -> BuildAgentEntrypoint:
    """The identical construction `_build_agent_with_prompt` already
    establishes, with `llm_gateway` swapped for a caller-supplied
    (real, controllable) `_FlakyLLMGateway` instead of a bare
    `EchoLLMGateway()` — needed only by the two general-step-retry
    proof tests below, where the LLM call itself must genuinely fail."""
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=llm_gateway,
            prompt_engine=InMemoryPromptEngine(templates={(prompt_id, "0.1.0"): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _documentation_agent_with_prompt(template: str, prompt_id: str) -> DocumentationAgentEntrypoint:
    """documentation is migrated onto the Platform SDK (step 13) — the
    fifth and final migration. Construct zero-arg, exactly as
    ``EntrypointLoader`` does (this agent needs no ``working_directory``
    override at all — see its own module docstring for why it always
    reuses the caller-supplied one), then bind the real ``PackContext``
    a real caller would inject, granting both ``llm:invoke`` and
    ``sandbox:execute`` — the identical permission shape ``build`` (step
    12) already proved. No ``python_command`` to supply (step 12a) —
    ``ToolInvokerAdapter`` resolves the real, portable interpreter
    invocation itself, from the same ``LocalSubprocessSandbox`` instance
    passed to ``build_pack_context`` below, automatically."""
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


@pytest.mark.asyncio
async def test_all_six_agent_steps_and_both_gates_genuinely_chain_through_real_persisted_outputs(
    tmp_path: Path, database_url: str
) -> None:
    """The real end-to-end proof this step exists for: a real, declared
    eight-step WorkflowDefinition (six agent steps, two blocking quality
    gates), driven to completion, in which each step's genuine output is
    proven — by inspecting the final artifact, not by a test
    hand-copying anything — to have reached the next step's genuine
    input, including both real quality gates (`quality-gate-lint-clean`,
    `quality-gate-tests-pass`) genuinely passing on genuinely clean
    code."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # {{context}} (Requirements Analyst's own real, echoed output, for
    # architecture_template — Architecture's own real, JSON-quoted
    # output, for build_template) is deliberately placed in a
    # comment-like prefix *before* the FILE_PATH marker, never inside
    # the generated file's own Python string literal —
    # `_parse_build_instruction` finds the FILE_PATH/...END block
    # anywhere in the completion, so this proves the real hand-off
    # (readable back from `instruction`) without making the *written
    # file's* own validity depend on what upstream free text happens to
    # contain (quotes, newlines).
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        'print("hello from the pipeline")\n'
        "FILE_CONTENT_END"
    )

    documentation_template = (
        "# {{filePath}}\n\n"
        "Instruction: {{instruction}}\n"
        "Passed: {{passed}} (exit {{exitCode}})\n"
        "Output: {{output}}"
    )

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

        requirements_analyst_outputs = next(
            s.outputs for s in steps if s.step_name == "requirements-analyst"
        )
        assert requirements_analyst_outputs is not None
        # The raw top-level `requirement` genuinely reached Requirements
        # Analyst's own real prompt — read back from its own persisted
        # `analysis` field, not hand-copied.
        assert "print a friendly message" in requirements_analyst_outputs["analysis"]

        architecture_outputs = next(s.outputs for s in steps if s.step_name == "architecture")
        assert architecture_outputs is not None
        # Requirements Analyst's own real output genuinely reached
        # Architecture's own real prompt — the new hand-off this feature
        # step adds — read back from Architecture's own persisted
        # `content` field, not hand-copied.
        assert "ANALYSIS: refined and structured" in architecture_outputs["content"]
        # via 2-hop {{context}}
        assert "print a friendly message" in architecture_outputs["content"]

        build_outputs = next(s.outputs for s in steps if s.step_name == "build")
        assert build_outputs is not None
        # The full chain, read back three hops downstream: Architecture's
        # own real output (which itself embeds Requirements Analyst's own
        # real output, which itself embeds the raw top-level requirement)
        # genuinely reached Build's own real prompt — not hand-copied,
        # read back from Build's own persisted `instruction` field (its
        # raw completion text).
        assert "DESIGN: a single Python script" in build_outputs["instruction"]
        assert "ANALYSIS: refined and structured" in build_outputs["instruction"]
        assert "print a friendly message" in build_outputs["instruction"]  # via 3-hop {{context}}

        # Lint genuinely ran `python -m py_compile` against the real file
        # Build wrote — and the second real proof this step exists for:
        # the gate mechanism genuinely generalized to this second,
        # distinct category (Static Analysis) via configuration alone.
        lint_outputs = next(s.outputs for s in steps if s.step_name == "lint")
        assert lint_outputs is not None
        assert lint_outputs["passed"] is True
        assert lint_outputs["exitCode"] == 0

        lint_gate_outputs = next(
            s.outputs for s in steps if s.step_name == "quality-gate-lint-clean"
        )
        assert lint_gate_outputs is not None
        assert lint_gate_outputs["passed"] is True

        # The real proof this feature step exists for: both real,
        # passing gates each genuinely wrote their own
        # evaluation.gate_results row — the Evaluation Engine's first
        # real consumer, not merely a workflow_steps-level record.
        for gate_step_id in ("quality-gate-lint-clean", "quality-gate-tests-pass"):
            rows = await _real_gate_results(
                engine, workflow_id=result.last_instance.workflow_id, step_id=gate_step_id
            )
            assert len(rows) == 1
            row = rows[0]
            assert row.gate_id == gate_step_id
            # se.delivery_pipeline's own real, current definition version —
            # read from the instance itself, never hardcoded, so this
            # assertion survives the next version bump unchanged.
            assert row.gate_version == result.last_instance.definition_version
            assert row.status == "completed"
            assert row.severity == "blocking"
            assert row.metrics == {"attempt": 1}
            assert row.messages == []
            assert row.duration_ms == 0  # honest: started_at == completed_at at this write path

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


@pytest.mark.asyncio
async def test_a_genuinely_failing_test_run_halts_the_pipeline_before_documentation(
    tmp_path: Path, database_url: str
) -> None:
    """The real proof this feature step (the Quality Gate Engine's
    smallest real slice) exists for: a build that genuinely fails when
    run halts the pipeline at the new `quality-gate-tests-pass` step —
    Documentation is never invoked, not merely skipped by convention or
    asserted from this test's own knowledge of what "should" happen."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # Genuinely fails when run — exit code 1, not a syntax error or a
    # sandbox/timeout failure, so `test`'s own `passed` field is real,
    # data-driven `False`, the same "derived only from exitCode/timeout"
    # contract `verification.py` already documents. Genuinely valid
    # syntax (py_compile's own real check, the `lint` gate's tool),
    # so this scenario reaches `test` unblocked, as intended.
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        "import sys\n"
        "sys.exit(1)\n"
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
                build_template, "build.write_file", working_directory=tmp_path
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.FAILED
        assert result.error is not None
        assert isinstance(result.error, QualityGateFailedError)
        assert "quality-gate-tests-pass" in str(result.error)

        assert result.last_instance is not None
        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        # The gate's own real source: `test` genuinely ran and genuinely
        # failed — not skipped, not mocked.
        test_outputs = next(s.outputs for s in steps if s.step_name == "test")
        assert test_outputs is not None
        assert test_outputs["passed"] is False
        assert test_outputs["exitCode"] == 1

        # Every genuinely failed gate attempt is genuinely persisted
        # (the observability-gap fix, 2026-07-30) — at least one real,
        # distinct "failed" row, not silently discarded.
        gate_rows = [s for s in steps if s.step_name == "quality-gate-tests-pass"]
        assert len(gate_rows) >= 1
        for gate_row in gate_rows:
            assert gate_row.status == "failed"
            assert gate_row.error is not None

        # The other real proof this feature step exists for: every one
        # of those same real, failed attempts also genuinely wrote its
        # own evaluation.gate_results row — reading it back and tying it
        # directly to the identical, already-asserted workflow_steps
        # error, not a second, independent guess at what happened.
        gate_result_rows = await _real_gate_results(
            engine,
            workflow_id=result.last_instance.workflow_id,
            step_id="quality-gate-tests-pass",
        )
        assert len(gate_result_rows) == len(gate_rows)
        for gate_row, result_row in zip(
            sorted(gate_rows, key=lambda s: s.attempt),
            sorted(gate_result_rows, key=lambda r: r.metrics["attempt"]),
            strict=True,
        ):
            assert result_row.gate_id == "quality-gate-tests-pass"
            assert result_row.gate_version == result.last_instance.definition_version
            assert result_row.status == "failed"
            assert result_row.severity == "blocking"
            assert result_row.metrics == {"attempt": gate_row.attempt}
            assert gate_row.error is not None
            assert result_row.messages == [gate_row.error["message"]]

        # The real proof this step blocks progression, not merely
        # records the failure after the fact: Documentation never runs.
        assert not any(s.step_name == "documentation" for s in steps)
        assert not (tmp_path / "solution.py.md").exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_gate_failure_within_the_retry_bound_eventually_succeeds(
    tmp_path: Path, database_url: str
) -> None:
    """The real proof this step exists for: a build that genuinely
    fails on its first real run but genuinely succeeds on a real
    retry — a controllable, deterministic flaky condition (a marker
    file on disk), not a coin flip. `delivery_pipeline.yaml`'s own
    `retryPolicy` (`maxAttempts: 2`) allows exactly the one retry this
    needs; the pipeline completes within the bound, Documentation
    genuinely runs.

    **Also the real proof for the observability-gap step (added
    2026-07-30): the gate's own first, genuinely failed attempt is now
    genuinely persisted, not silently discarded.** `record_failed_attempt`
    means `quality-gate-tests-pass` now has two real, distinct
    `workflow_steps` rows — attempt 1, `status="failed"` with real
    error detail, and attempt 2, `status="completed"` with
    `passed=True` — not just the one, eventually-successful row this
    test used to see before that fix."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # Build's own rendered output is identical on every attempt (a
    # static template, Echo-backed) — what's genuinely flaky is the
    # *generated script's own execution*: it fails the first time it
    # ever runs (creating a real marker file on disk), then succeeds
    # every time after, once that marker exists. This models a real,
    # transient reason a retry can genuinely help (error_handling_retry.md
    # §3's own `transient` category), without any randomness.
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        "import pathlib\n"
        "import sys\n"
        "marker = pathlib.Path(__file__).resolve().parent / 'retry_marker.txt'\n"
        "if marker.exists():\n"
        "    print('second attempt: succeeding')\n"
        "else:\n"
        "    marker.write_text('first attempt ran')\n"
        "    sys.exit(1)\n"
        "FILE_CONTENT_END"
    )
    documentation_template = (
        "# {{filePath}}\n\nInstruction: {{instruction}}\nPassed: {{passed}} (exit {{exitCode}})"
    )

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

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.COMPLETED
        assert result.error is None
        assert result.last_instance is not None

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        # build genuinely ran twice — a real second attempt, not skipped.
        build_rows = [s for s in steps if s.step_name == "build"]
        assert sorted(s.attempt for s in build_rows) == [1, 2]

        # test genuinely ran twice too, and its own real outcome flipped
        # from failing to passing between the two real runs.
        test_rows = sorted((s for s in steps if s.step_name == "test"), key=lambda s: s.attempt)
        first_test_outputs, second_test_outputs = test_rows[0].outputs, test_rows[1].outputs
        assert first_test_outputs is not None
        assert second_test_outputs is not None
        assert first_test_outputs["passed"] is False
        assert first_test_outputs["exitCode"] == 1
        assert second_test_outputs["passed"] is True
        assert second_test_outputs["exitCode"] == 0

        # The real proof this feature step exists for: the gate's own
        # first, genuinely failed attempt is now genuinely persisted —
        # a real, distinct row, not silently discarded — alongside the
        # second, passing attempt.
        gate_rows = sorted(
            (s for s in steps if s.step_name == "quality-gate-tests-pass"),
            key=lambda s: s.attempt,
        )
        assert [s.attempt for s in gate_rows] == [1, 2]

        failed_gate_row, passed_gate_row = gate_rows
        assert failed_gate_row.status == "failed"
        assert failed_gate_row.outputs is None
        assert failed_gate_row.error is not None
        assert failed_gate_row.error["type"] == "QualityGateFailedError"
        assert "quality-gate-tests-pass" in failed_gate_row.error["message"]

        assert passed_gate_row.status == "completed"
        assert passed_gate_row.error is None
        gate_outputs = passed_gate_row.outputs
        assert gate_outputs is not None
        assert gate_outputs["passed"] is True

        # Documentation genuinely ran — the pipeline completed, not just
        # "didn't crash."
        doc_file = tmp_path / "solution.py.md"
        assert doc_file.is_file()
        assert "Passed: true" in doc_file.read_text(encoding="utf-8")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_gate_that_fails_every_attempt_exhausts_the_retry_bound_and_halts(
    tmp_path: Path, database_url: str
) -> None:
    """The other real proof this step exists for: a build that
    genuinely fails on *every* attempt exhausts `retryPolicy`'s own
    `maxAttempts: 2` bound and genuinely halts the pipeline —
    Documentation never runs, and `test`/`build` are never attempted a
    third time (not an infinite loop)."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        "import sys\n"
        "sys.exit(1)\n"
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
                build_template, "build.write_file", working_directory=tmp_path
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.FAILED
        assert isinstance(result.error, QualityGateFailedError)
        assert result.last_instance is not None

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        # Exactly retryPolicy.maxAttempts (2) real attempts — never a
        # third. This is the genuinely-bounded proof: without a real
        # bound this would loop forever, since the build never succeeds.
        build_rows = [s for s in steps if s.step_name == "build"]
        test_rows = [s for s in steps if s.step_name == "test"]
        assert sorted(s.attempt for s in build_rows) == [1, 2]
        assert sorted(s.attempt for s in test_rows) == [1, 2]
        for test_row in test_rows:
            assert test_row.outputs is not None
            assert test_row.outputs["passed"] is False

        # Both genuinely failed gate attempts are now genuinely
        # persisted (the observability-gap fix, 2026-07-30) — real,
        # distinct "failed" rows, not silently discarded just because
        # the bound was exhausted. Documentation never ran — the real
        # proof this halts, not silently continues.
        gate_rows = [s for s in steps if s.step_name == "quality-gate-tests-pass"]
        assert sorted(s.attempt for s in gate_rows) == [1, 2]
        for gate_row in gate_rows:
            assert gate_row.status == "failed"
            assert gate_row.outputs is None
            assert gate_row.error is not None
            assert gate_row.error["type"] == "QualityGateFailedError"
        assert not any(s.step_name == "documentation" for s in steps)
        assert not (tmp_path / "solution.py.md").exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_non_gate_step_failure_within_the_retry_bound_eventually_succeeds(
    tmp_path: Path, database_url: str
) -> None:
    """The real proof this feature step exists for: general,
    error-category-driven step retry, widened beyond quality gates to
    `build` itself — the same bounded mechanism gates already proved,
    reused unchanged. `build`'s own LLM call raises a real, retriable
    `LLMProviderError` (its own documented default) on its first real
    attempt, then succeeds — the real production `_STEP_RETRY_TARGETS`
    (`ai_os_kernel.workflow_engine.delivery_pipeline`) retries `build`
    from itself and the pipeline completes, the identical way a failed
    gate already does."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        'print("hello from the pipeline")\n'
        "FILE_CONTENT_END"
    )
    documentation_template = (
        "# {{filePath}}\n\nInstruction: {{instruction}}\nPassed: {{passed}} (exit {{exitCode}})"
    )

    flaky_build_gateway = _FlakyLLMGateway(EchoLLMGateway(), failures_before_success=1)

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                requirements_analyst_template, "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                architecture_template, "architecture.propose_design"
            ),
            _AGENT_IDS["build"]: _build_agent_with_flaky_llm_gateway(
                build_template,
                "build.write_file",
                working_directory=tmp_path,
                llm_gateway=flaky_build_gateway,
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
            _AGENT_IDS["git-push"]: _unconfigured_git_push_agent(),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.COMPLETED
        assert result.error is None
        assert result.last_instance is not None
        assert flaky_build_gateway.attempts == 2  # one real failure, one real retry

        written_file = tmp_path / "solution.py"
        assert written_file.is_file()
        assert (
            written_file.read_text(encoding="utf-8").strip() == 'print("hello from the pipeline")'
        )

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        # build genuinely ran twice — a real second attempt, not skipped.
        build_rows = sorted((s for s in steps if s.step_name == "build"), key=lambda s: s.attempt)
        assert [s.attempt for s in build_rows] == [1, 2]
        failed_build_row, passed_build_row = build_rows

        # The genuinely failed first attempt is now genuinely persisted
        # (the observability-gap fix, 2026-07-30) — a real, distinct
        # "failed" row, not silently discarded.
        assert failed_build_row.status == "failed"
        assert failed_build_row.outputs is None
        assert failed_build_row.error is not None
        assert failed_build_row.error["type"] == "LLMProviderError"

        assert passed_build_row.status == "completed"
        assert passed_build_row.outputs is not None

        # Downstream steps genuinely ran on the real, successful retry —
        # the pipeline completed, not just "didn't crash."
        lint_outputs = next(s.outputs for s in steps if s.step_name == "lint")
        assert lint_outputs is not None
        assert lint_outputs["passed"] is True
        doc_file = tmp_path / "solution.py.md"
        assert doc_file.is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_genuinely_non_retriable_step_failure_halts_immediately_despite_a_configured_target(
    tmp_path: Path, database_url: str
) -> None:
    """The other real proof this feature step exists for: `build` has a
    real, configured retry target (`_STEP_RETRY_TARGETS["build"] ==
    "build"` — the identical production config the retry-then-succeed
    test above exercises), but a failure explicitly classified
    non-retriable (`LLMProviderError(..., retriable=False)`,
    llm_gateway.md §10's own `permanent`/`budget` rows) must never
    retry anyway. Proves the retriability check — not merely a
    configured target — genuinely gates the decision, end to end
    against the real production pipeline and its real config, not only
    at the unit level."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    documentation_template = "# {{filePath}}\n\nInstruction: {{instruction}}"

    # `failures_before_success` set absurdly high is irrelevant here —
    # `retriable=False` alone must prevent even a single retry.
    always_failing_gateway = _FlakyLLMGateway(
        EchoLLMGateway(), failures_before_success=10_000, retriable=False
    )

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                requirements_analyst_template, "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                architecture_template, "architecture.propose_design"
            ),
            _AGENT_IDS["build"]: _build_agent_with_flaky_llm_gateway(
                "irrelevant — the LLM call always raises before this is used",
                "build.write_file",
                working_directory=tmp_path,
                llm_gateway=always_failing_gateway,
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.FAILED
        assert isinstance(result.error, LLMProviderError)
        assert always_failing_gateway.attempts == 1  # no retry at all, despite a configured target
        assert result.last_instance is not None

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        build_rows = [s for s in steps if s.step_name == "build"]
        assert len(build_rows) == 1  # exactly one attempt — no retry
        assert build_rows[0].status == "failed"
        assert build_rows[0].error is not None
        assert build_rows[0].error["type"] == "LLMProviderError"

        assert not any(s.step_name == "lint" for s in steps)
        assert not any(s.step_name == "documentation" for s in steps)
        assert not (tmp_path / "solution.py").exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_genuinely_lint_violating_build_halts_retries_and_exhausts_before_test_runs(
    tmp_path: Path, database_url: str
) -> None:
    """The real proof this feature step exists for: a build that
    genuinely, persistently fails a real `python -m py_compile` check
    halts the pipeline at `quality-gate-lint-clean` — retries once (per
    the existing bounded mechanism, proven generic in the prior step),
    then genuinely exhausts the bound (the violation is never fixed,
    since the real Build Agent's own template is static) and halts for
    good. `test`/`quality-gate-tests-pass`/`documentation` never run at
    all — a stronger halt than the Test gate's own exhausted case,
    since Lint sits earlier in the pipeline."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # A real, deterministic syntax error — never fixed across attempts,
    # since this template is static; genuinely exhausts the bound
    # rather than a coin flip.
    build_template = (
        "Upstream design: {{context}}\n\n"
        "FILE_PATH: solution.py\n"
        "FILE_CONTENT_BEGIN\n"
        "def f(:\n"
        "    pass\n"
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
                build_template, "build.write_file", working_directory=tmp_path
            ),
            _AGENT_IDS["lint"]: _lint_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["test"]: _test_agent_with_sandbox(LocalSubprocessSandbox()),
            _AGENT_IDS["documentation"]: _documentation_agent_with_prompt(
                documentation_template, "documentation.record_artifact"
            ),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_pipeline_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )

        result = await trigger({"requirement": "print a friendly message"}, "test-principal")

        assert result.outcome == WorkflowRunOutcome.FAILED
        assert isinstance(result.error, QualityGateFailedError)
        assert "quality-gate-lint-clean" in str(result.error)
        assert result.last_instance is not None

        engine_repo = SqlWorkflowInstanceRepository(engine)
        steps = await engine_repo.list_steps(result.last_instance.workflow_id)

        # Exactly retryPolicy.maxAttempts (2) real attempts at build/lint
        # — never a third: the genuinely-bounded proof.
        build_rows = [s for s in steps if s.step_name == "build"]
        lint_rows = [s for s in steps if s.step_name == "lint"]
        assert sorted(s.attempt for s in build_rows) == [1, 2]
        assert sorted(s.attempt for s in lint_rows) == [1, 2]
        for lint_row in lint_rows:
            assert lint_row.outputs is not None
            assert lint_row.outputs["passed"] is False

        # Both genuinely failed lint-gate attempts are now genuinely
        # persisted (the observability-gap fix, 2026-07-30) — real,
        # distinct "failed" rows.
        lint_gate_rows = [s for s in steps if s.step_name == "quality-gate-lint-clean"]
        assert sorted(s.attempt for s in lint_gate_rows) == [1, 2]
        for lint_gate_row in lint_gate_rows:
            assert lint_gate_row.status == "failed"
            assert lint_gate_row.outputs is None
            assert lint_gate_row.error is not None
            assert lint_gate_row.error["type"] == "QualityGateFailedError"

        # Lint sits before Test in this pipeline — a failing lint gate
        # must halt before Test ever runs, not just before Documentation.
        assert not any(s.step_name == "test" for s in steps)
        assert not any(s.step_name == "quality-gate-tests-pass" for s in steps)
        assert not any(s.step_name == "documentation" for s in steps)
        assert not (tmp_path / "solution.py.md").exists()
    finally:
        await engine.dispose()


async def _register_and_activate_pack(database_url: str) -> None:
    """**``pack_root=PACK_ROOT`` (added this step) genuinely derives and
    writes this pack's real ``catalog.agents``/``catalog.prompts``/
    ``catalog.tools`` rows** — see
    ``ai_os_kernel.capability_manager.manifest_catalog_installer``. This
    replaces both ``_seed_agent_rows`` and ``_seed_real_prompts``
    (removed) — the exact hand-duplicated raw-SQL seeding this
    initiative's own prior feature-step report flagged by name.

    **A real, discovered bug in the raw SQL this replaces, not merely
    stale duplication**: ``_seed_agent_rows`` granted
    ``sandbox:execute`` to `requirements-analyst`/`architecture`
    uniformly with `build`/`documentation`, even though neither of the
    first two actually declares that permission in the real manifest —
    over-permissive, silently harmless only because neither agent ever
    tries to use a tool. The real installer derives each agent's own
    exact, correct permission set instead — see
    ``manifest_catalog_installer.py``'s own docstring, and
    ``tests/integration/capability_manager/test_manifest_catalog_installer.py``
    for the dedicated proof."""
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
                pack_root=PACK_ROOT,
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
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
    end of a real, five-step run starting from Requirements Analyst."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)

        engine = build_engine(database_url)
        try:
            llm_gateway, prompt_engine = await _build_real_llm_gateway_and_prompt_engine(engine)
            registry = SqlAgentRegistry(
                engine, llm_gateway=llm_gateway, prompt_engine=prompt_engine
            )
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
            requirements_analyst_step = next(
                s for s in steps if s.step_name == "requirements-analyst"
            )
            build_step = next(s for s in steps if s.step_name == "build")
            documentation_step = next(s for s in steps if s.step_name == "documentation")
            assert requirements_analyst_step.outputs is not None
            assert requirements_analyst_step.outputs["analysis"].strip() != ""
            assert build_step.outputs is not None
            assert documentation_step.outputs is not None

            working_directory = Path(build_step.outputs["workingDirectory"])
            documentation_path = working_directory / documentation_step.outputs["documentationPath"]
            assert documentation_path.is_file()
            assert documentation_path.read_text(encoding="utf-8").strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
