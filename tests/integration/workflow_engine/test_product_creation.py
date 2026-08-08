"""Real, Postgres-backed, end-to-end proof that ``se.product_creation``'s
own buildable 7-step prefix (``P08-S02-M30-T01``) genuinely runs to
completion: requirements-analyst -> quality-gate-requirements-complete
(honest no-op pass, `QualityGateStepExecutor`'s own documented behaviour
for an unconfigured gate id) -> approve-requirements (pauses, then
resumes via a real `ApprovalService` decision) -> architecture ->
quality-gate-architecture-compliance (honest no-op pass) ->
approve-architecture (pauses/resumes identically) -> technical-planner,
reaching `WorkflowRunOutcome.COMPLETED`. See
``kernel/src/ai_os_kernel/workflow_engine/product_creation.py`` and
``capability_packs/software-engineering/workflows/product_creation.yaml``
for why this workflow stops at step 7 of the documented 14-step graph.

Deterministic tier only — `InMemoryAgentRegistry`, `EchoLLMGateway`
backed, no pack registration/activation needed at all, the identical
shape `test_delivery_pipeline.py`'s own deterministic tier already
establishes. No sandbox-needing agent exists in this workflow (all three
steps are prompted, `llm:invoke`-only agents), so this test needs no
Docker/`LocalSubprocessSandbox` either.

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
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, SqlApprovalRepository
from ai_os_kernel.workflow_engine.product_creation import (
    build_product_creation_trigger,
    resume_product_creation_after_approval,
)
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalystAgentEntrypoint,
)
from ai_os_pack_software_engineering.agents.technical_planner import (
    TechnicalPlannerAgentEntrypoint,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

_AGENT_IDS = {
    "requirements-analyst": f"{_PACK_ID}/requirements-analyst",
    "architecture": f"{_PACK_ID}/architecture",
    "technical-planner": f"{_PACK_ID}/technical-planner",
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
async def test_the_seven_step_prefix_genuinely_runs_to_completion(database_url: str) -> None:
    """Drives the real, declared ``se.product_creation`` workflow through
    both real Human Approval Points to genuine completion, proving each
    step's real, persisted output reached the next step's real input —
    by reading it back from a later step's own real, persisted output,
    never by hand-copying anything — for both real hand-offs this
    workflow's own ``_STEP_SOURCES``/``_FIELD_SELECTORS`` wiring declares
    (``architecture`` reads ``requirements-analyst.analysis``;
    ``technical-planner`` reads ``architecture.content``)."""

    requirements_analyst_template = "ANALYSIS: refined and structured.\nRaw ask was: {{context}}"
    architecture_template = "DESIGN: a single Python script.\nContext was: {{context}}"
    # A literal, already-valid JSON array — no ``{{context}}`` needed;
    # see this module's own docstring for why embedding upstream free
    # text inside a JSON string here would risk invalid JSON.
    technical_planner_template = (
        '[{"title": "Implement the approved design", '
        '"description": "Build it per the approved architecture."}]'
    )

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
        }
    )

    engine = build_engine(database_url)
    try:
        trigger = build_product_creation_trigger(engine, registry)
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
            engine, registry, workflow_id=workflow_id
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
            engine, registry, workflow_id=workflow_id
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
    finally:
        await engine.dispose()
