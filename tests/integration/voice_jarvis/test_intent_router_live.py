"""``PlatformIntentRouter`` against a real Postgres container (ADR-0015
— no mocking the database) — proves the whole real stack
(`SqlWorkflowInstanceRepository`/`SqlApprovalRepository`, not fakes)
genuinely works end to end, complementing the fake-backed unit tests
in ``tests/unit/kernel/voice_jarvis/test_intent_router.py``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.health import HealthService
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import approvals
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.voice_jarvis.errors import VoiceIntentError
from ai_os_kernel.voice_jarvis.intent_router import PlatformIntentRouter
from ai_os_kernel.voice_jarvis.models import VoiceIntent
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, SqlApprovalRepository
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


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


async def _seed_workflow_instance(engine: AsyncEngine, workflow_id: str) -> None:
    definition_id = f"def_voice_{uuid.uuid4().hex}"
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, pack_id, version, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, 'test-pack', '1.0.0', "
                " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now())"
            ),
            {"definition_id": definition_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO workflow.workflow_instances "
                "(workflow_id, definition_id, definition_version, status, "
                " inputs, principal_id, last_event_seq) "
                "VALUES (:workflow_id, :definition_id, '1.0.0', 'waiting_for_human', "
                " '{}'::jsonb, 'user_test', 0)"
            ),
            {"workflow_id": workflow_id, "definition_id": definition_id},
        )


async def _seed_pending_approval(
    engine: AsyncEngine, *, workflow_id: str, approval_id: str
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(approvals),
            {
                "approval_id": approval_id,
                "workflow_id": workflow_id,
                "step_id": "step_1",
                "approval_class": "approve-git-push",
                "title": "A real approval",
                "description": "A real description",
                "context_digest": "deadbeef",
                "options": ["approved", "rejected"],
                "status": "pending",
                "decided_by": None,
                "decision_comment": None,
                "requested_at": datetime.now(UTC),
                "expires_at": None,
                "decided_at": None,
            },
        )


def _router(engine: AsyncEngine) -> PlatformIntentRouter:
    return PlatformIntentRouter(
        health_service=HealthService(checks=[]),
        workflow_instance_repository=SqlWorkflowInstanceRepository(engine),
        approval_service=ApprovalService(SqlApprovalRepository(engine)),
    )


def test_get_workflow_status_against_a_real_seeded_instance(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_voice_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)

            result = await _router(engine).handle(
                VoiceIntent(intent_type="get_workflow_status", workflow_id=workflow_id),
                principal=Principal(
                    principal_id="voice-live-test",
                    principal_type=PrincipalType.USER,
                    roles=frozenset({"viewer"}),
                ),
            )

            assert workflow_id in result.response_text
            assert "waiting_for_human" in result.response_text
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_decide_approval_against_a_real_seeded_pending_approval(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_voice_{uuid.uuid4().hex}"
            approval_id = f"appr_voice_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)
            await _seed_pending_approval(engine, workflow_id=workflow_id, approval_id=approval_id)

            result = await _router(engine).handle(
                VoiceIntent(
                    intent_type="decide_approval", approval_id=approval_id, decision="approved"
                ),
                principal=Principal(
                    principal_id="voice-live-test",
                    principal_type=PrincipalType.USER,
                    roles=frozenset({"admin"}),
                ),
            )

            assert result.response_text == f"Approval {approval_id} was approved."
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_decide_approval_refuses_an_unauthorized_principal_against_real_data(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_voice_{uuid.uuid4().hex}"
            approval_id = f"appr_voice_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)
            await _seed_pending_approval(engine, workflow_id=workflow_id, approval_id=approval_id)

            with pytest.raises(VoiceIntentError, match="not authorized"):
                await _router(engine).handle(
                    VoiceIntent(
                        intent_type="decide_approval", approval_id=approval_id, decision="approved"
                    ),
                    principal=Principal(
                        principal_id="voice-live-test",
                        principal_type=PrincipalType.USER,
                        roles=frozenset({"viewer"}),
                    ),
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
