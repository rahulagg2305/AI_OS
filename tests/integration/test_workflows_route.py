"""Deterministic, real-database verification that the minimal Security
Manager slice genuinely fronts the real Workflow Engine — both the
existing write trigger and this step's new read routes — through the
real composition root (``bootstrap.build_app()`` + ``_lifespan``), not
a hand-assembled equivalent, and not the no-database unit tests in
``tests/unit/kernel/routes/test_workflows.py``.

No real Anthropic credential is used for the write-path tests: the demo
agent is therefore never registered, so an authorized request reaches
all the way through authentication, authorization, and the real
Workflow Engine machinery, and gets a real, structured ``failed``
outcome back — proving the security boundary does not block or distort
a legitimate request, while staying deterministic. The read-route test
drives a real instance to a genuine ``completed`` state first (a
substituted Echo-backed agent, the identical technique
``test_bootstrap_workflow_trigger.py`` uses — no live Anthropic
credential needed either), then reads it back exclusively through the
authenticated HTTP routes. The opt-in live counterpart,
``test_workflows_route_live.py``, proves the full write path all the
way to a genuine Anthropic-backed ``completed`` result.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

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

from ai_os_kernel.bootstrap import (
    _DEMO_WORKFLOW_PROMPT_ID,
    _DEMO_WORKFLOW_PROMPT_VERSION,
    _PROMPTED_AGENT_ID,
    _build_demo_workflow_definition,
    _build_workflow_trigger,
    build_app,
)
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.resolvers import WorkflowStateResolver
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"
_GREETING_TEMPLATE = "Hello from the read-routes smoke test!"


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
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "integration-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_an_authorized_request_reaches_the_real_workflow_engine(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"]
    # No real Anthropic credential is configured, so the demo agent was
    # never registered — a real, structured failure, not a security
    # boundary rejection (which would be 401/403) or a crash.
    assert body["outcome"] == "failed"
    assert "no agent registered" in body["error"]


def test_an_unauthorized_request_never_reaches_the_workflow_engine(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403


async def _drive_a_completed_instance(database_url: str) -> str:
    """Bypasses HTTP entirely: the identical Echo-agent-substitution
    technique ``test_bootstrap_workflow_trigger.py`` uses, so the read
    routes below have a genuinely ``completed`` instance — with a real
    step and real events — to read back, without needing a live
    Anthropic credential."""
    engine = build_engine(database_url)
    try:
        prompt_engine = InMemoryPromptEngine(
            {(_DEMO_WORKFLOW_PROMPT_ID, _DEMO_WORKFLOW_PROMPT_VERSION): _GREETING_TEMPLATE}
        )
        service = PromptedCompletionService(
            prompt_engine=prompt_engine, llm_gateway=EchoLLMGateway()
        )
        agent = PromptedAgent(service=service, max_output_tokens=1024)
        registry = InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})
        context_manager = DefaultContextManager(
            resolvers=[WorkflowStateResolver(SqlWorkflowInstanceRepository(engine))]
        )
        trigger = _build_workflow_trigger(engine, registry, context_manager)

        result = await trigger({}, "read-routes-test-principal")

        assert result.outcome is WorkflowRunOutcome.COMPLETED
        return result.workflow_id
    finally:
        await engine.dispose()


def test_the_read_routes_return_a_real_completed_instance_through_the_http_layer(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow_id = asyncio.run(_drive_a_completed_instance(database_url))

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {_token(['viewer'])}"}

        detail_response = client.get(f"/api/v1/workflows/{workflow_id}", headers=headers)
        steps_response = client.get(f"/api/v1/workflows/{workflow_id}/steps", headers=headers)
        events_response = client.get(f"/api/v1/workflows/{workflow_id}/events", headers=headers)
        manifest_response = client.get(
            f"/api/v1/workflows/{workflow_id}/run_manifest", headers=headers
        )

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["workflow_id"] == workflow_id
    assert detail["status"] == "completed"

    assert steps_response.status_code == 200
    steps = steps_response.json()
    assert len(steps) == 1
    assert steps[0]["agent_id"] == _PROMPTED_AGENT_ID
    assert steps[0]["outputs"] == {"content": _GREETING_TEMPLATE}

    assert events_response.status_code == 200
    events = events_response.json()
    event_types = [event["event_type"] for event in events]
    assert "workflow.started" in event_types
    assert "workflow.completed" in event_types

    # `_build_workflow_trigger` genuinely wires a real
    # `SqlRunManifestRecorder`, so a genuinely completed instance has a
    # real, recorded manifest to read back — not a fabricated one.
    assert manifest_response.status_code == 200
    manifest_body = manifest_response.json()
    assert manifest_body["manifest_hash"].startswith("sha256:")
    assert manifest_body["manifest"]["workflow_id"] == workflow_id
    assert [entry["agent_id"] for entry in manifest_body["manifest"]["steps"]] == [
        _PROMPTED_AGENT_ID
    ]


def test_the_read_routes_report_404_for_a_workflow_id_that_never_existed(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {_token(['viewer'])}"}

        detail_response = client.get("/api/v1/workflows/wf_never_existed", headers=headers)
        steps_response = client.get("/api/v1/workflows/wf_never_existed/steps", headers=headers)
        events_response = client.get("/api/v1/workflows/wf_never_existed/events", headers=headers)
        manifest_response = client.get(
            "/api/v1/workflows/wf_never_existed/run_manifest", headers=headers
        )

    assert detail_response.status_code == 404
    assert steps_response.status_code == 404
    assert events_response.status_code == 404
    assert manifest_response.status_code == 404


def test_the_run_manifest_route_is_honestly_404_for_a_real_instance_that_never_completed(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _create_uncompleted_instance() -> str:
        engine = build_engine(database_url)
        try:
            definition = _build_demo_workflow_definition()
            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id=definition.id,
                definition_version=definition.version,
                inputs={},
                principal_id="run-manifest-404-test-principal",
            )
            return instance.workflow_id
        finally:
            await engine.dispose()

    workflow_id = asyncio.run(_create_uncompleted_instance())

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/workflows/{workflow_id}/run_manifest",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    # A real, distinct 404 reason from the "never existed" case above —
    # the instance is genuinely real, just never reached completion, so
    # `record()` was never called for it.
    assert response.status_code == 404
    assert "no run manifest recorded" in response.json()["detail"]


def test_list_workflows_paginates_through_every_instance_with_no_duplicates_or_gaps(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    created_ids = {asyncio.run(_drive_a_completed_instance(database_url)) for _ in range(3)}

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['viewer'])}"}

    seen_ids: list[str] = []
    cursor: str | None = None
    with TestClient(app) as client:
        for _ in range(1000):  # a generous, finite ceiling — never expected to be reached
            params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
            response = client.get("/api/v1/workflows", params=params, headers=headers)

            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) <= 2

            seen_ids.extend(item["workflow_id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        else:
            pytest.fail("pagination did not terminate within 1000 pages")

    # Every instance this test (and any earlier test sharing this
    # module's container) created is visible exactly once — real
    # keyset pagination duplicates or skips nothing across pages.
    assert len(seen_ids) == len(set(seen_ids))
    assert created_ids.issubset(set(seen_ids))


def test_list_workflows_rejects_a_malformed_cursor_end_to_end(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/workflows",
            params={"cursor": "not-a-real-cursor"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 400
