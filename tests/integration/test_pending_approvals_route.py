"""Real, Postgres-backed, end-to-end proof of the one real gap
``human_approval.py``'s own module docstring named as "real, separate,
later work" (``P06-S03-M39-T02``): ``SqlApprovalRepository.list_pending()``
and the new ``GET /api/v1/approvals`` route it backs
(api_architecture.md §6.2: "Pending approvals").

Proves: a real, persisted ``pending`` approval genuinely appears in
both the repository's own real list and the real HTTP route's own real
response; a real, decided approval genuinely does not (`list_pending`
only ever selects ``status = 'pending'`` rows); the real route refuses
an unauthenticated request and a real, authenticated principal holding
neither ``approver`` nor ``admin`` (`viewer`), and serves a real,
authenticated ``approver``/``admin`` principal — the same real
``approval:read`` permission gate ``permissions.py`` now grants only
where authentication_authorization.md §4.2's own role table actually
mentions approvals.

**Also covers ``GET /api/v1/approvals/{approval_id}`` (added
2026-08-10, `P06-S04-M38-T01`)** — a single approval by id, over the
same real ``approval:read`` gate and the already-real
``SqlApprovalRepository.get_by_id`` read (previously exercised only
indirectly, via the decide route), closing the CLI's own disclosed
``approve show`` gap.

**Also covers ``GET /api/v1/approvals/history`` (added 2026-08-10,
`P06-S04-M38-T01` revisited)** — the last of api_architecture.md
§6.2's own 4 documented Approvals endpoints. Real, keyset-paginated
(``SqlApprovalRepository.list_decided``, backed by the new
``ix_approvals_decided_at`` index, migration
``0037_approvals_decided_at_index``) — deliberately not the pending
queue's unpaginated shape, since decided approvals accumulate for the
platform's whole life.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

from __future__ import annotations

import asyncio
import os
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
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.human_approval import (
    ApprovalListCursor,
    SqlApprovalRepository,
)
from ai_os_kernel.workflow_engine.models import HumanApprovalPoint, WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.run_manifest_recorder import SqlRunManifestRecorder
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "pending-approvals-route-test-signing-key-at-least-32-bytes"  # gitleaks:allow
_PACK_ID = "se.software_engineering"
_DEFINITION_ID = "se.pending_approvals_test"


def _definition(version: str) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Pending Approvals Test Fixture",
            "description": "test fixture",
            "version": version,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "approve-it", "type": "human_approval"}],
            "humanApprovalPoints": [
                {
                    "id": "approve-it",
                    "name": "Approve It",
                    "description": "test fixture",
                    "context": {},
                    "options": ["approve", "reject"],
                }
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


def _point(approval_id: str) -> HumanApprovalPoint:
    return HumanApprovalPoint(
        id=approval_id,
        name="Approve It",
        description="test fixture",
        context={},
        options=["approve", "reject"],
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
    return PlatformConfig(env="test", role="api", manifest_schema_path=SCHEMA_PATH)


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "pending-approvals-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


async def _create_real_instance(engine: AsyncEngine, *, version: str) -> str:
    """The smallest real ``WorkflowInstance`` — enough to satisfy
    ``approvals.workflow_id``'s own real FK to ``workflow_instances``,
    never an unmocked/fabricated id."""
    repository = SqlWorkflowInstanceRepository(engine)
    service = WorkflowInstanceService(
        repository=repository,
        step_executor=NoOpStepExecutor(),
        definition_catalog=SqlWorkflowDefinitionCatalog(engine),
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    instance = await service.create_instance(
        definition=_definition(version),
        inputs={},
        principal_id="test-principal",
        pack_id=_PACK_ID,
    )
    await service.start(workflow_id=instance.workflow_id, reason="test fixture")
    # decide()'s own guarded UPDATE requires the real instance to
    # genuinely be `waiting_for_human` — the identical real
    # precondition a genuine `human_approval` step execution leaves
    # behind, reused directly here rather than driving a full executor.
    await repository.mark_waiting_for_human(
        workflow_id=instance.workflow_id,
        definition_id=instance.definition_id,
        definition_version=instance.definition_version,
        expected_current_step_id=None,
        reason="test fixture",
    )
    return instance.workflow_id


def test_list_pending_includes_pending_and_excludes_decided(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)

            pending_workflow_id = await _create_real_instance(engine, version="1.0.0")
            pending = await approval_repository.create_pending(
                workflow_id=pending_workflow_id,
                step_id="approve-it",
                point=_point("approve-it"),
            )

            decided_workflow_id = await _create_real_instance(engine, version="1.0.1")
            decided = await approval_repository.create_pending(
                workflow_id=decided_workflow_id,
                step_id="approve-it",
                point=_point("approve-it"),
            )
            await approval_repository.decide(
                approval_id=decided.approval_id,
                principal_id="test-principal",
                decision="approved",
                comment=None,
            )

            all_pending = await approval_repository.list_pending()
            pending_ids = {approval.approval_id for approval in all_pending}

            assert pending.approval_id in pending_ids
            assert decided.approval_id not in pending_ids
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_pending_orders_oldest_first(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)
            workflow_id = await _create_real_instance(engine, version="1.0.2")
            first = await approval_repository.create_pending(
                workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            # A real, second pending approval against a genuinely
            # different workflow instance (the same definition's own
            # `(workflow_id, step_name)` pair cannot repeat without a
            # second real instance — the identical uniqueness this
            # codebase's own step-attempt constraint already enforces
            # for `workflow_steps`).
            second_workflow_id = await _create_real_instance(engine, version="1.0.3")
            second = await approval_repository.create_pending(
                workflow_id=second_workflow_id, step_id="approve-it", point=_point("approve-it")
            )

            all_pending = await approval_repository.list_pending()
            ids_in_order = [a.approval_id for a in all_pending]
            assert ids_in_order.index(first.approval_id) < ids_in_order.index(second.approval_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_get_approvals_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real token verifier must be configured for an absent/invalid
    # token to be genuinely refused with 401 — without one, `authenticate`
    # itself cannot run at all, and the route correctly reports 503
    # ("auth not configured"), a materially different, honest failure
    # this same suite's other tests are not exercising here.
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get("/api/v1/approvals")
    assert response.status_code == 401


def test_get_approvals_route_refuses_a_principal_without_approval_read(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/approvals", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        )
    assert response.status_code == 403


def test_get_approvals_route_serves_real_pending_approvals_to_an_authorized_principal(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _seed() -> tuple[str, str]:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_instance(engine, version="1.0.4")
            approval = await SqlApprovalRepository(engine).create_pending(
                workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            return workflow_id, approval.approval_id
        finally:
            await engine.dispose()

    workflow_id, approval_id = asyncio.run(_seed())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        approver_response = client.get(
            "/api/v1/approvals",
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )
        admin_response = client.get(
            "/api/v1/approvals", headers={"Authorization": f"Bearer {_token(['admin'])}"}
        )

    assert approver_response.status_code == 200
    assert admin_response.status_code == 200
    approver_ids = {a["approval_id"] for a in approver_response.json()["approvals"]}
    assert approval_id in approver_ids
    matching = next(
        a for a in approver_response.json()["approvals"] if a["approval_id"] == approval_id
    )
    assert matching["workflow_id"] == workflow_id
    assert matching["status"] == "pending"


def test_get_approval_by_id_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get("/api/v1/approvals/does-not-matter")
    assert response.status_code == 401


def test_get_approval_by_id_route_refuses_a_principal_without_approval_read(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/approvals/does-not-matter",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert response.status_code == 403


def test_get_approval_by_id_route_returns_404_for_a_real_unknown_id(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/approvals/does-not-exist",
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )
    assert response.status_code == 404


def test_get_approval_by_id_route_serves_the_real_approval_to_an_authorized_principal(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _seed() -> tuple[str, str]:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_instance(engine, version="1.0.5")
            approval = await SqlApprovalRepository(engine).create_pending(
                workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            return workflow_id, approval.approval_id
        finally:
            await engine.dispose()

    workflow_id, approval_id = asyncio.run(_seed())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/approvals/{approval_id}",
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_id"] == approval_id
    assert body["workflow_id"] == workflow_id
    assert body["status"] == "pending"


def test_list_decided_excludes_pending_and_includes_decided(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)

            pending_workflow_id = await _create_real_instance(engine, version="1.1.0")
            pending = await approval_repository.create_pending(
                workflow_id=pending_workflow_id,
                step_id="approve-it",
                point=_point("approve-it"),
            )

            decided_workflow_id = await _create_real_instance(engine, version="1.1.1")
            decided = await approval_repository.create_pending(
                workflow_id=decided_workflow_id,
                step_id="approve-it",
                point=_point("approve-it"),
            )
            await approval_repository.decide(
                approval_id=decided.approval_id,
                principal_id="test-principal",
                decision="approved",
                comment=None,
            )

            history = await approval_repository.list_decided(limit=50)
            history_ids = {approval.approval_id for approval in history}

            assert decided.approval_id in history_ids
            assert pending.approval_id not in history_ids
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_decided_orders_newest_decision_first(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)

            first_workflow_id = await _create_real_instance(engine, version="1.1.2")
            first = await approval_repository.create_pending(
                workflow_id=first_workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            await approval_repository.decide(
                approval_id=first.approval_id,
                principal_id="test-principal",
                decision="approved",
                comment=None,
            )

            second_workflow_id = await _create_real_instance(engine, version="1.1.3")
            second = await approval_repository.create_pending(
                workflow_id=second_workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            await approval_repository.decide(
                approval_id=second.approval_id,
                principal_id="test-principal",
                decision="rejected",
                comment=None,
            )

            history = await approval_repository.list_decided(limit=50)
            ids_in_order = [a.approval_id for a in history]
            # Newest decision first — the opposite fairness convention
            # from `list_pending`'s own oldest-first queue (see
            # `list_decided`'s own docstring for why).
            assert ids_in_order.index(second.approval_id) < ids_in_order.index(first.approval_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_decided_paginates_with_a_real_keyset_cursor(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)
            decided_ids: list[str] = []
            for i in range(3):
                workflow_id = await _create_real_instance(engine, version=f"1.1.{4 + i}")
                approval = await approval_repository.create_pending(
                    workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
                )
                decided = await approval_repository.decide(
                    approval_id=approval.approval_id,
                    principal_id="test-principal",
                    decision="approved",
                    comment=None,
                )
                decided_ids.append(decided.approval_id)

            first_page = await approval_repository.list_decided(limit=2)
            assert len(first_page) == 2
            last = first_page[-1]
            assert last.decided_at is not None
            cursor = ApprovalListCursor(decided_at=last.decided_at, approval_id=last.approval_id)

            second_page = await approval_repository.list_decided(limit=2, before=cursor)
            # Real keyset pagination, not offset in disguise: the two
            # pages share no row, and together cover every real,
            # decided row created in this test (no skip, no duplicate).
            first_page_ids = {a.approval_id for a in first_page}
            second_page_ids = {a.approval_id for a in second_page}
            assert first_page_ids.isdisjoint(second_page_ids)
            assert set(decided_ids) <= (first_page_ids | second_page_ids)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_get_approval_history_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get("/api/v1/approvals/history")
    assert response.status_code == 401


def test_get_approval_history_route_refuses_a_principal_without_approval_read(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/approvals/history",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert response.status_code == 403


def test_get_approval_history_route_serves_a_real_decided_approval(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _seed() -> str:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_instance(engine, version="1.1.7")
            approval_repository = SqlApprovalRepository(engine)
            approval = await approval_repository.create_pending(
                workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
            )
            decided = await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="test-principal",
                decision="approved",
                comment=None,
            )
            return decided.approval_id
        finally:
            await engine.dispose()

    approval_id = asyncio.run(_seed())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # A generous limit: other tests in this module-scoped-database
        # file also decide real approvals, so this asserts the real,
        # specific row genuinely appears somewhere in a real response,
        # not that it is the only one.
        response = client.get(
            "/api/v1/approvals/history",
            params={"limit": 100},
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    matching = next(item for item in body["items"] if item["approval_id"] == approval_id)
    assert matching["status"] == "approved"


def test_get_approval_history_route_next_cursor_genuinely_advances_the_page(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _seed_two_decided() -> None:
        engine = build_engine(database_url)
        try:
            approval_repository = SqlApprovalRepository(engine)
            for i in range(2):
                workflow_id = await _create_real_instance(engine, version=f"1.1.{8 + i}")
                approval = await approval_repository.create_pending(
                    workflow_id=workflow_id, step_id="approve-it", point=_point("approve-it")
                )
                await approval_repository.decide(
                    approval_id=approval.approval_id,
                    principal_id="test-principal",
                    decision="approved",
                    comment=None,
                )
        finally:
            await engine.dispose()

    asyncio.run(_seed_two_decided())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        first_response = client.get(
            "/api/v1/approvals/history",
            params={"limit": 1},
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )
        assert first_response.status_code == 200
        first_body = first_response.json()
        assert len(first_body["items"]) == 1
        next_cursor = first_body["next_cursor"]
        assert next_cursor is not None

        # A real cursor genuinely round-trips through the HTTP boundary,
        # not just the repository layer's own direct test above — the
        # second page's first item must differ from the first page's.
        second_response = client.get(
            "/api/v1/approvals/history",
            params={"limit": 1, "cursor": next_cursor},
            headers={"Authorization": f"Bearer {_token(['admin'])}"},
        )
    assert second_response.status_code == 200
    second_body = second_response.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["approval_id"] != first_body["items"][0]["approval_id"]


def test_get_approval_history_route_rejects_a_malformed_cursor(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/approvals/history",
            params={"cursor": "not-a-real-cursor"},
            headers={"Authorization": f"Bearer {_token(['approver'])}"},
        )
    assert response.status_code == 400
