"""Real, Postgres-backed, end-to-end proof that ``se.product_creation``'s
own buildable 8-step prefix (``P08-S02-M30-T01``) genuinely runs to
completion: requirements-analyst -> quality-gate-requirements-complete
(honest no-op pass, `QualityGateStepExecutor`'s own documented behaviour
for an unconfigured gate id) -> approve-requirements (pauses, then
resumes via a real `ApprovalService` decision) -> architecture ->
quality-gate-architecture-compliance (honest no-op pass) ->
approve-architecture (pauses/resumes identically) -> technical-planner ->
implement-tasks (a real `foreach` step, genuinely fanning out into one
real, separate, completed `se.implement_task` child instance per
planned task), reaching `WorkflowRunOutcome.COMPLETED`. See
``kernel/src/ai_os_kernel/workflow_engine/product_creation.py`` and
``capability_packs/software-engineering/workflows/product_creation.yaml``
for why this workflow stops at step 8 of the documented 14-step graph.

Deterministic tier only — `InMemoryAgentRegistry`, `EchoLLMGateway`
backed, no pack registration/activation needed at all, the identical
shape `test_delivery_pipeline.py`'s own deterministic tier already
establishes. `build`/`qa-test`/`code-review` (the real
`se.implement_task` child this workflow now fans out into) genuinely
need a real, local sandbox — `LocalSubprocessSandbox`, no Docker — the
identical no-Docker-needed shape `test_implement_task.py`'s own
deterministic tier already establishes for that same trio.

**technical-planner's own real parser (`_parse_tasks`) requires its
completion to be a bare JSON array, not free text.** Its own test
template below is supplied as a literal, already-valid JSON array string
with no `{{context}}` placeholder, so `EchoLLMGateway`'s own
literal-echo-the-rendered-prompt behaviour (the identical mechanism
`_requirements_analyst_agent_with_prompt`/`_architecture_agent_with_prompt`
already rely on) satisfies it directly — no custom fake gateway needed,
unlike `test_delivery_pipeline.py`'s own `_BuildCompatibleEchoGateway`,
because `requirements-analyst`/`architecture` accept any free text and
`technical-planner`'s own fixed template already IS valid JSON.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, SqlApprovalRepository
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.product_creation import (
    build_product_creation_trigger,
    resume_product_creation_after_approval,
)
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.code_review import CodeReviewerAgentEntrypoint
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalystAgentEntrypoint,
)
from ai_os_pack_software_engineering.agents.technical_planner import (
    TechnicalPlannerAgentEntrypoint,
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
    "technical-planner": f"{_PACK_ID}/technical-planner",
    "build": f"{_PACK_ID}/build",
    "qa-test": f"{_PACK_ID}/qa-test",
    "code-review": f"{_PACK_ID}/code-review",
}

# A real, valid, empty findings array — the identical "template IS the
# completion" convention `test_implement_task.py`'s own
# `_CODE_REVIEW_CLEAN_TEMPLATE` already relies on for `EchoLLMGateway`.
_CODE_REVIEW_CLEAN_TEMPLATE = "[]"
_PASSING_SCRIPT_TEMPLATE = (
    'FILE_PATH: solution.py\nFILE_CONTENT_BEGIN\nprint("ok")\nFILE_CONTENT_END'
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
    """Mirrors ``test_delivery_pipeline.py``'s own helper of the same
    name exactly — construct zero-arg, then bind the real ``PackContext``
    a real caller would inject, granting exactly ``llm:invoke``."""
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
    """Mirrors ``test_delivery_pipeline.py``'s own helper of the same
    name exactly."""
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


def _technical_planner_agent_with_prompt(
    template: str, prompt_id: str
) -> TechnicalPlannerAgentEntrypoint:
    """The identical zero-arg-construct-then-bind shape the two helpers
    above already establish — ``technical-planner`` is real, SDK-native,
    ``llm:invoke``-only, exactly like its two upstream siblings."""
    agent = TechnicalPlannerAgentEntrypoint()
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


def _build_agent(template: str, *, working_directory: Path) -> BuildAgentEntrypoint:
    """Mirrors ``test_implement_task.py``'s own helper of the same
    name exactly — the real per-child ``implement`` agent
    ``se.implement_task``'s own workflow declares."""
    agent = BuildAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={("build.write_file", "0.1.0"): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _qa_test_agent() -> TestAgentEntrypoint:
    """Mirrors ``test_implement_task.py``'s own helper of the same
    name exactly."""
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
    """Mirrors ``test_implement_task.py``'s own helper of the same
    name exactly."""
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


async def _approve(engine: AsyncEngine, *, workflow_id: str, step_id: str) -> None:
    """Finds the real, pending approval for ``step_id`` and decides it
    ``approved`` via the real ``ApprovalService`` — mirrors
    ``test_delivery_pipeline.py``'s own real approval-decision sequence
    (``get_by_step`` -> ``ApprovalService.decide``), using the ``admin``
    role rather than a class-scoped ``approver:<class>`` role, since
    this test approves two distinct approval classes
    (``approve-requirements``/``approve-architecture``) with the same
    principal."""
    approval_repository = SqlApprovalRepository(engine)
    pending = await approval_repository.get_by_step(workflow_id=workflow_id, step_id=step_id)
    assert pending is not None, step_id
    approval_service = ApprovalService(approval_repository)
    principal = Principal(
        principal_id="product-owner",
        principal_type=PrincipalType.USER,
        roles=frozenset({"admin"}),
    )
    decided = await approval_service.decide(
        approval_id=pending.approval_id,
        principal=principal,
        decision="approved",
        comment="Deterministic proof run — no real review needed.",
    )
    assert decided.status == "approved"


@pytest.mark.asyncio
async def test_the_eight_step_workflow_genuinely_runs_to_completion(
    tmp_path: Path, database_url: str
) -> None:
    """Drives the real, declared ``se.product_creation`` workflow through
    both real Human Approval Points and its own real ``foreach`` step to
    genuine completion, proving each step's real, persisted output
    reached the next step's real input — by reading it back from a
    later step's own real, persisted output, never by hand-copying
    anything — for both real hand-offs this workflow's own
    ``_STEP_SOURCES``/``_FIELD_SELECTORS`` wiring declares
    (``architecture`` reads ``requirements-analyst.analysis``;
    ``technical-planner`` reads ``architecture.content``), plus the new
    real hand-off step 8 makes: ``implement-tasks`` (``foreach``) reads
    ``technical-planner``'s own real ``tasks`` list and genuinely fans
    out into one real, separate, completed ``se.implement_task`` child
    instance per task (`P08-S02-M30-T01`)."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # A literal, already-valid JSON array — no ``{{context}}`` needed;
    # see this module's own docstring for why embedding upstream free
    # text inside a JSON string here would risk invalid JSON. Exactly
    # one task keeps the real child fan-out this test also proves small
    # and easy to assert on precisely.
    technical_planner_template = (
        '[{"title": "Implement the approved design", '
        '"description": "Build it per the approved architecture."}]'
    )
    python_command = LocalSubprocessSandbox().python_command

    registry = InMemoryAgentRegistry(
        {
            _AGENT_IDS["requirements-analyst"]: _requirements_analyst_agent_with_prompt(
                requirements_analyst_template, "requirements.analyze"
            ),
            _AGENT_IDS["architecture"]: _architecture_agent_with_prompt(
                architecture_template, "architecture.propose_design"
            ),
            _AGENT_IDS["technical-planner"]: _technical_planner_agent_with_prompt(
                technical_planner_template, "technicalplanning.produce_plan"
            ),
            _AGENT_IDS["build"]: _build_agent(_PASSING_SCRIPT_TEMPLATE, working_directory=tmp_path),
            _AGENT_IDS["qa-test"]: _qa_test_agent(),
            _AGENT_IDS["code-review"]: _code_review_agent(_CODE_REVIEW_CLEAN_TEMPLATE),
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_product_creation_trigger(engine, registry, python_command=python_command)
        repository = SqlWorkflowInstanceRepository(engine)

        result = await trigger(
            {"specification": "- Users can shorten a URL\n- Users can view click counts\n"},
            "test-principal",
        )

        assert result.outcome == WorkflowRunOutcome.WAITING_FOR_HUMAN, result.error
        assert result.last_instance is not None
        workflow_id = result.last_instance.workflow_id

        steps = await repository.list_steps(workflow_id)
        requirements_outputs = next(
            s.outputs for s in steps if s.step_name == "requirements-analyst"
        )
        assert requirements_outputs is not None
        assert "Users can shorten a URL" in requirements_outputs["analysis"]

        await _approve(engine, workflow_id=workflow_id, step_id="approve-requirements")

        result = await resume_product_creation_after_approval(
            engine, registry, workflow_id=workflow_id, python_command=python_command
        )
        assert result.outcome == WorkflowRunOutcome.WAITING_FOR_HUMAN, result.error

        steps = await repository.list_steps(workflow_id)
        architecture_outputs = next(s.outputs for s in steps if s.step_name == "architecture")
        assert architecture_outputs is not None
        # Requirements Analyst's own real, persisted `analysis` genuinely
        # reached Architecture's own real rendered prompt.
        assert "ANALYSIS: refined and structured" in architecture_outputs["content"]

        await _approve(engine, workflow_id=workflow_id, step_id="approve-architecture")

        result = await resume_product_creation_after_approval(
            engine, registry, workflow_id=workflow_id, python_command=python_command
        )
        assert result.outcome == WorkflowRunOutcome.COMPLETED, result.error

        steps = await repository.list_steps(workflow_id)
        planner_outputs = next(s.outputs for s in steps if s.step_name == "technical-planner")
        assert planner_outputs is not None
        assert planner_outputs["tasks"] == [
            {
                "taskId": "task-1",
                "title": "Implement the approved design",
                "description": "Build it per the approved architecture.",
            }
        ]

        # Both real, disclosed no-op quality gates genuinely ran and
        # passed — proving `QualityGateStepExecutor`'s own documented
        # "an unconfigured gate id resolves as a pass with empty
        # outputs" behaviour, not a fabricated pass/fail signal.
        gate_step = next(s for s in steps if s.step_name == "quality-gate-requirements-complete")
        assert gate_step.outputs == {}
        gate_step = next(s for s in steps if s.step_name == "quality-gate-architecture-compliance")
        assert gate_step.outputs == {}

        # The real proof this step adds: `implement-tasks` (`foreach`)
        # genuinely read `technical-planner`'s own real `tasks` list and
        # fanned out into one real, separate, completed
        # `se.implement_task` child instance per task.
        foreach_outputs = next(s.outputs for s in steps if s.step_name == "implement-tasks")
        assert foreach_outputs is not None
        assert foreach_outputs["subWorkflowId"] == "se.implement_task"
        assert foreach_outputs["itemCount"] == 1
        assert len(foreach_outputs["results"]) == 1

        child_workflow_id = foreach_outputs["results"][0]["childWorkflowId"]
        assert child_workflow_id != workflow_id
        child_instance = await repository.get_instance(child_workflow_id)
        assert child_instance is not None
        assert child_instance.status == WorkflowInstanceStatus.COMPLETED
        assert child_instance.definition_id == "se.implement_task"
        # The real item technical-planner produced became the real
        # child instance's own persisted inputs, straight through, no
        # transform — `ForeachStepExecutor`'s own documented contract.
        assert child_instance.inputs == {
            "taskId": "task-1",
            "title": "Implement the approved design",
            "description": "Build it per the approved architecture.",
        }

        child_steps = await repository.list_steps(child_workflow_id)
        assert {s.step_name for s in child_steps} == {
            "implement",
            "qa-test",
            "tests-passed",
            "code-review",
            "no-blocking-findings",
            "quality-gate-tests-pass",
        }
        child_gate = next(
            s.outputs for s in child_steps if s.step_name == "quality-gate-tests-pass"
        )
        assert child_gate == {
            "gateId": "quality-gate-tests-pass",
            "sourceStepId": "qa-test",
            "passed": True,
        }
    finally:
        await engine.dispose()
