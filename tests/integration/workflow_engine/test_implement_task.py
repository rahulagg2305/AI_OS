"""Real, Postgres-backed, end-to-end proof that ``se.implement_task``
(``P08-S02-M30-T02``) genuinely runs: implement -> qa-test ->
`tests-passed` (a real, genuinely-looping `decision` step) -> code-review
-> `no-blocking-findings` (a second real, genuinely-looping `decision`
step) -> `quality-gate-tests-pass` (a real, configured gate reading
qa-test's own real `passed` field), reaching
`WorkflowRunOutcome.COMPLETED`. See
``kernel/src/ai_os_kernel/workflow_engine/implement_task.py`` and
``capability_packs/software-engineering/workflows/implement_task.yaml``
for why this workflow diverges from workflows.md §4's own documented
graph (no `backend-developer` agent, no `fs.apply_patch`/`test.run`
tool steps, no per-loop attempt counter).

Two real scenarios, mirroring `test_product_creation.py`'s own
deterministic-tier shape (`InMemoryAgentRegistry`, no pack registration
needed):

1. The straight-through happy path — Build's own first attempt already
   writes a passing script, so both decision steps branch forward on
   their very first evaluation and the run completes without ever
   looping back.
2. **The real loop-back proof** — Build's own first attempt writes a
   script that fails (`sys.exit(1)`), so `tests-passed` genuinely
   branches backward to `implement`; a real, controllable, attempt-
   counting fake gateway (`_FlakyBuildGateway`, mirroring
   `test_delivery_pipeline.py`'s own `_FlakyLLMGateway` technique)
   returns a passing script on the second call, proving the same
   `step_name` genuinely re-executes with a fresh, higher `attempt` and
   the run recovers to `COMPLETED`.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse, StopReason, UsageRecord
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.implement_task import build_implement_task_trigger
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.code_review import CodeReviewerAgentEntrypoint
from ai_os_pack_software_engineering.agents.verification import TestAgentEntrypoint
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

_AGENT_IDS = {
    "build": f"{_PACK_ID}/build",
    "qa-test": f"{_PACK_ID}/qa-test",
    "code-review": f"{_PACK_ID}/code-review",
}

# A real, valid, empty findings array — the identical "template IS the
# completion" convention `test_delivery_pipeline.py`'s own
# `_CODE_REVIEW_CLEAN_TEMPLATE` already relies on for `EchoLLMGateway`.
_CODE_REVIEW_CLEAN_TEMPLATE = "[]"

_PASSING_SCRIPT_CONTENT = (
    'FILE_PATH: solution.py\nFILE_CONTENT_BEGIN\nprint("ok")\nFILE_CONTENT_END'
)
_FAILING_SCRIPT_CONTENT = (
    "FILE_PATH: solution.py\nFILE_CONTENT_BEGIN\nimport sys\nsys.exit(1)\nFILE_CONTENT_END"
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


def _build_agent(
    llm_gateway: KernelLLMGatewayProtocol, template: str, *, working_directory: Path
) -> BuildAgentEntrypoint:
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=llm_gateway,
            prompt_engine=InMemoryPromptEngine(templates={("build.write_file", "0.1.0"): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _qa_test_agent() -> TestAgentEntrypoint:
    agent = TestAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _code_review_agent(template: str) -> CodeReviewerAgentEntrypoint:
    agent = CodeReviewerAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(
                templates={("codereview.produce_findings", "0.1.0"): template}
            ),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


class _FlakyBuildGateway:
    """First call returns a script that exits 1 (a genuine, real test
    failure); every subsequent call returns a script that exits 0 — the
    real, controllable condition needed to prove `tests-passed`'s own
    decision step genuinely branches backward to `implement` and a
    second attempt genuinely recovers. Mirrors
    `test_delivery_pipeline.py`'s own `_FlakyLLMGateway` attempt-counting
    technique, applied to real script content instead of a raised
    exception."""

    def __init__(self) -> None:
        self.attempts = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.attempts += 1
        content = _FAILING_SCRIPT_CONTENT if self.attempts == 1 else _PASSING_SCRIPT_CONTENT
        return LLMResponse(
            content=content,
            stop_reason=StopReason.END_TURN,
            usage=UsageRecord(
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=0,
                provider="echo",
                model_id="echo-1",
                retries=0,
                fallback_used=False,
            ),
            provider="echo",
            model_id="echo-1",
            model_version="1.0.0",
        )


@pytest.mark.asyncio
async def test_the_happy_path_completes_without_looping(tmp_path: Path, database_url: str) -> None:
    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["build"]: _build_agent(
                EchoLLMGateway(), _PASSING_SCRIPT_CONTENT, working_directory=tmp_path
            ),
            _AGENT_IDS["qa-test"]: _qa_test_agent(),
            _AGENT_IDS["code-review"]: _code_review_agent(_CODE_REVIEW_CLEAN_TEMPLATE),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_implement_task_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )
        repository = SqlWorkflowInstanceRepository(engine)

        result = await trigger(
            {"title": "Print ok", "description": "Write a script that prints ok"}, "test-principal"
        )

        assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error
        assert result.last_instance is not None
        workflow_id = result.last_instance.workflow_id

        steps = await repository.list_steps(workflow_id)
        assert {s.step_name for s in steps} == {
            "implement",
            "qa-test",
            "tests-passed",
            "code-review",
            "no-blocking-findings",
            "quality-gate-tests-pass",
        }
        qa_test_output = next(s.outputs for s in steps if s.step_name == "qa-test")
        assert qa_test_output is not None
        assert qa_test_output["passed"] is True

        gate_output = next(s.outputs for s in steps if s.step_name == "quality-gate-tests-pass")
        assert gate_output == {
            "gateId": "quality-gate-tests-pass",
            "sourceStepId": "qa-test",
            "passed": True,
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_failing_first_attempt_genuinely_loops_back_and_recovers(
    tmp_path: Path, database_url: str
) -> None:
    flaky_gateway = _FlakyBuildGateway()
    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["build"]: _build_agent(
                flaky_gateway,
                "unused — _FlakyBuildGateway ignores the rendered prompt",
                working_directory=tmp_path,
            ),
            _AGENT_IDS["qa-test"]: _qa_test_agent(),
            _AGENT_IDS["code-review"]: _code_review_agent(_CODE_REVIEW_CLEAN_TEMPLATE),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_implement_task_trigger(
            engine, registry, python_command=LocalSubprocessSandbox().python_command
        )
        repository = SqlWorkflowInstanceRepository(engine)

        result = await trigger(
            {"title": "Print ok", "description": "Write a script that prints ok"}, "test-principal"
        )

        assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error
        assert flaky_gateway.attempts == 2, "the second implement attempt must genuinely happen"
        assert result.last_instance is not None
        workflow_id = result.last_instance.workflow_id

        steps = await repository.list_steps(workflow_id)
        implement_attempts = sorted(s.attempt for s in steps if s.step_name == "implement")
        assert implement_attempts == [1, 2], "implement must genuinely re-execute once"

        qa_test_by_attempt = {
            s.attempt: s.outputs for s in steps if s.step_name == "qa-test" and s.outputs
        }
        assert qa_test_by_attempt[1]["passed"] is False
        assert qa_test_by_attempt[2]["passed"] is True

        final_gate = next(s.outputs for s in steps if s.step_name == "quality-gate-tests-pass")
        assert final_gate == {
            "gateId": "quality-gate-tests-pass",
            "sourceStepId": "qa-test",
            "passed": True,
        }
    finally:
        await engine.dispose()
