"""Real, genuine proof of ``human_approval`` step execution
(``P03-S05-M14-T04``/``T05``) against a real Postgres container
(ADR-0015 — no mocking the database) — the last of the seven step
types to genuinely execute.

Proves: a real workflow genuinely pauses at a `human_approval` step and
stays genuinely paused — not a single check, but repeatedly, across
real wall-clock time and real, separate `advance()`/lease-acquire
attempts — until a real, attributable decision is recorded through
:meth:`~ai_os_kernel.workflow_engine.human_approval.
SqlApprovalRepository.decide`, at which point it genuinely resumes and
completes; that a real `timeout` elapsing **never** implies approval —
R-001's own permanent hard rule (`risk_register.md`) — the pending
approval and the paused instance are still exactly as they were, real
wall-clock time later, with no decision recorded; that an anonymous
(blank `principal_id`) or a double decision attempt is refused, never
silently accepted; that a real `rejected` decision genuinely halts the
pipeline before any step after it ever runs; and (`P03-S05-M14-T06`)
that :class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`
enforces ADR-0023's real, class-scoped `approver:<approval_class>` RBAC
against a real Postgres row — an authorized principal decides, an
unauthorized one is refused and the row stays genuinely `pending`.
"""

import asyncio
import os
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import approvals
from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner, WorkflowRunOutcome
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import ApprovalNotPendingError
from ai_os_kernel.workflow_engine.human_approval import (
    ApprovalService,
    HumanApprovalStepExecutor,
    SqlApprovalRepository,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.human_approval_test"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"
_STEP_ID = "approve-deployment"

# `register()` is an upsert keyed on `(definition_id, version)` with
# `ON CONFLICT DO NOTHING` (data_model.md §5: versions are immutable —
# a change creates a new version row, definition_catalog.py's own
# docstring). Every test in this module shares `database_url` (module
# scope, one real container), so a definition with different content —
# here, a declared `timeout` — MUST use its own version; reusing
# `_DEFINITION_VERSION` would silently resolve to whichever test
# registered that version first, not the content this test declared.
# Must be strict semver (`WorkflowDefinition.version`'s own pattern).
_TIMEOUT_DEFINITION_VERSION = "1.0.1"


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


def _definition(*, timeout: float | None = None) -> WorkflowDefinition:
    point: dict[str, Any] = {
        "id": _STEP_ID,
        "name": "Approve Deployment",
        "description": "Approve the production deployment.",
        "context": {"target": "prod"},
        "options": ["approve", "reject"],
    }
    if timeout is not None:
        point["timeout"] = timeout
    version = _TIMEOUT_DEFINITION_VERSION if timeout is not None else _DEFINITION_VERSION
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Human Approval Test",
            "description": "test fixture",
            "version": version,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": _STEP_ID, "type": "human_approval"},
                {"id": "finish", "type": "tool", "toolId": "se.noop"},
            ],
            "humanApprovalPoints": [point],
            "failureHandling": {"onError": "halt"},
        }
    )


class _EchoStepExecutor:
    """A real ``StepExecutor`` that always succeeds — stands in for the
    ``finish`` step so this file's own scope stays the human_approval
    step, not a real tool/agent invocation."""

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        return {"status": "ok"}


def _make_composition(
    engine: AsyncEngine,
) -> tuple[WorkflowAdvanceRunner, SqlApprovalRepository, SqlWorkflowInstanceRepository]:
    repository = SqlWorkflowInstanceRepository(engine)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    approval_repository = SqlApprovalRepository(engine)
    human_approval_executor = HumanApprovalStepExecutor(
        approval_repository=approval_repository,
        instance_repository=repository,
        definition_catalog=definition_catalog,
    )
    step_executor = DispatchingStepExecutor(
        agent_executor=NoOpStepExecutor(),
        tool_executor=_EchoStepExecutor(),
        default_executor=NoOpStepExecutor(),
        human_approval_executor=human_approval_executor,
    )
    instance_service = WorkflowInstanceService(repository, step_executor, definition_catalog)
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    return advance_runner, approval_repository, repository


async def _create_running_instance(engine: AsyncEngine, definition: WorkflowDefinition) -> str:
    await SqlWorkflowDefinitionCatalog(engine).register(definition=definition, pack_id=_PACK_ID)
    repository = SqlWorkflowInstanceRepository(engine)
    created = await repository.create(
        definition_id=definition.id,
        definition_version=definition.version,
        inputs={},
        principal_id="user-42",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    return created.workflow_id


async def _approval_status(engine: AsyncEngine, workflow_id: str) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(approvals.c.status).where(
                approvals.c.workflow_id == workflow_id, approvals.c.step_id == _STEP_ID
            )
        )
        return str(result.scalar_one())


def test_a_workflow_genuinely_pauses_and_resumes_only_on_a_real_decision(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition()
            workflow_id = await _create_running_instance(engine, definition)
            advance_runner, approval_repository, repository = _make_composition(engine)

            # First real advance() call reaches the human_approval step
            # and genuinely pauses — never completes, never errors.
            result = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert result.outcome is WorkflowRunOutcome.WAITING_FOR_HUMAN
            assert result.last_instance is not None
            assert result.last_instance.status == WorkflowInstanceStatus.WAITING_FOR_HUMAN
            assert result.last_instance.current_step_id is None  # unchanged — step never completed
            assert await _approval_status(engine, workflow_id) == "pending"

            # Genuinely STILL paused — a second, entirely separate real
            # attempt (not a cached result) hits the same real outcome,
            # never silently progressing on its own.
            result_again = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert result_again.outcome is WorkflowRunOutcome.WAITING_FOR_HUMAN

            instance = await repository.get_instance(workflow_id)
            assert instance is not None
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None
            assert approval.status == "pending"

            # The one real, attributable decision that genuinely resumes it.
            decided = await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="user-99",
                decision="approved",
                comment="Looks good to ship.",
            )
            assert decided.status == "approved"
            assert decided.decided_by == "user-99"

            resumed_instance = await repository.get_instance(workflow_id)
            assert resumed_instance is not None
            assert resumed_instance.status == WorkflowInstanceStatus.RUNNING

            # The real, separate advance() call that genuinely completes
            # the pipeline — re-resolving the identical human_approval
            # step, this time finding the real decision, then advancing
            # past it to `finish`.
            final_result = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert final_result.outcome is WorkflowRunOutcome.COMPLETED

            steps = await repository.list_steps(workflow_id)
            approval_step = next(s for s in steps if s.step_name == _STEP_ID)
            assert approval_step.outputs == {
                "decision": "approved",
                "decidedBy": "user-99",
                "decisionComment": "Looks good to ship.",
                "decidedAt": decided.decided_at.isoformat() if decided.decided_at else None,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_timeout_never_implies_approval(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            # A short, real timeout — the point genuinely, provably
            # expires during this test's own real wall-clock sleep.
            definition = _definition(timeout=0.2)
            workflow_id = await _create_running_instance(engine, definition)
            advance_runner, approval_repository, repository = _make_composition(engine)

            result = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert result.outcome is WorkflowRunOutcome.WAITING_FOR_HUMAN

            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None
            assert approval.expires_at is not None

            # Real wall-clock time genuinely passes the declared timeout.
            await asyncio.sleep(0.4)
            assert time.time() > approval.expires_at.timestamp()

            # Nothing in this codebase ever sweeps an expired approval
            # into an implicit decision — it is still exactly `pending`,
            # and the instance is still exactly `waiting_for_human`,
            # real time later.
            assert await _approval_status(engine, workflow_id) == "pending"
            instance = await repository.get_instance(workflow_id)
            assert instance is not None
            assert instance.status == WorkflowInstanceStatus.WAITING_FOR_HUMAN

            # A further real advance() attempt, after the timeout has
            # elapsed, still only re-confirms the identical pause —
            # never a silent approval.
            result_after_timeout = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert result_after_timeout.outcome is WorkflowRunOutcome.WAITING_FOR_HUMAN
            assert await _approval_status(engine, workflow_id) == "pending"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_anonymous_or_double_decision_is_refused(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition()
            workflow_id = await _create_running_instance(engine, definition)
            advance_runner, approval_repository, _ = _make_composition(engine)

            await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None

            # An anonymous (blank) decision is refused outright — never
            # even reaches the database as a real decision.
            with pytest.raises(ValueError, match="non-empty, attributable principal_id"):
                await approval_repository.decide(
                    approval_id=approval.approval_id,
                    principal_id="   ",
                    decision="approved",
                    comment=None,
                )
            assert await _approval_status(engine, workflow_id) == "pending"

            # The one real, attributable decision.
            await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="user-99",
                decision="approved",
                comment=None,
            )

            # A second, real decision attempt against the identical,
            # already-decided approval is refused — never a silent
            # overwrite of an already-recorded, attributable decision.
            with pytest.raises(ApprovalNotPendingError):
                await approval_repository.decide(
                    approval_id=approval.approval_id,
                    principal_id="user-100",
                    decision="rejected",
                    comment="too late",
                )
            assert await _approval_status(engine, workflow_id) == "approved"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_rejected_decision_genuinely_halts_the_pipeline(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition()
            workflow_id = await _create_running_instance(engine, definition)
            advance_runner, approval_repository, repository = _make_composition(engine)

            await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None

            await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="user-99",
                decision="rejected",
                comment="Not ready for production.",
            )

            result = await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            assert result.outcome is WorkflowRunOutcome.FAILED

            steps = await repository.list_steps(workflow_id)
            step_names = {s.step_name for s in steps}
            assert "finish" not in step_names  # the pipeline never reached the next step
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_rbac_authorized_role_decides_and_unauthorized_role_is_refused_and_stays_pending(
    database_url: str,
) -> None:
    """(`P03-S05-M14-T06`) Real, Postgres-backed proof of ADR-0023's
    class-scoped `approver` grant, enforced by
    :class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`
    in front of the real repository — never the repository's own
    `decide()` directly, the identical "authorization sits in front of
    persistence" shape every other real authorization check in this
    codebase (`require_permission`, narrowing) already uses."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition()
            workflow_id = await _create_running_instance(engine, definition)
            advance_runner, approval_repository, _ = _make_composition(engine)

            await advance_runner.run_to_completion(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None

            service = ApprovalService(approval_repository)

            # Wrong class entirely — refused before any real write
            # against the real database; the row stays exactly pending.
            wrong_class = Principal(
                principal_id="user-1",
                principal_type=PrincipalType.USER,
                roles=frozenset({"approver:some-other-class"}),
            )
            with pytest.raises(ApprovalNotAuthorizedError):
                await service.decide(
                    approval_id=approval.approval_id,
                    principal=wrong_class,
                    decision="approved",
                    comment=None,
                )
            assert await _approval_status(engine, workflow_id) == "pending"

            # No roles at all — refused too.
            no_roles = Principal(
                principal_id="user-2", principal_type=PrincipalType.USER, roles=frozenset()
            )
            with pytest.raises(ApprovalNotAuthorizedError):
                await service.decide(
                    approval_id=approval.approval_id,
                    principal=no_roles,
                    decision="approved",
                    comment=None,
                )
            assert await _approval_status(engine, workflow_id) == "pending"

            # The real, class-scoped approver ADR-0023 documents
            # (`approver:<approval_class>`) genuinely, successfully
            # decides, and the real database reflects it.
            authorized = Principal(
                principal_id="user-99",
                principal_type=PrincipalType.USER,
                roles=frozenset({f"approver:{_STEP_ID}"}),
            )
            decided = await service.decide(
                approval_id=approval.approval_id,
                principal=authorized,
                decision="approved",
                comment="Looks good to ship.",
            )
            assert decided.status == "approved"
            assert decided.decided_by == "user-99"
            assert await _approval_status(engine, workflow_id) == "approved"
        finally:
            await engine.dispose()

    asyncio.run(_run())
