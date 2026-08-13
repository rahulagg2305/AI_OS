"""Real-database verification of ``POST /api/v1/voice/intent``
(``ai_os_kernel.routes.voice``) through the real composition root
(``bootstrap.build_app()`` + ``_lifespan``) — the identical shape
``test_gates_route.py``/``test_traceability_route.py`` already establish.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.

**What this file exists to prove.** `voice_jarvis` was risk register
R-018 item 5: real, tested code with zero production importers, no route
and no entry point — a whole subsystem unreachable from any running
process. Unit tests of `PlatformIntentRouter` could never have caught
that, because the gap was never in the router; it was that nothing
constructed one. So every test here goes through the real HTTP surface
of the real bootstrapped app, and the decisive assertion is not that the
router works (already proven) but that a real request genuinely reaches
it and comes back with the real platform's real state.
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

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"  # gitleaks:allow
_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"


def _minimal_workflow_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Product Creation (voice route test)",
            "description": "The smallest valid definition satisfying the real "
            "workflow_instances FK this test's direct repository call needs.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": "noop", "type": "agent", "agentId": "se.software_engineering/analyst"}
            ],
            "failureHandling": {"onError": "halt"},
        }
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


def _seed_real_instance(database_url: str) -> str:
    async def _seed() -> str:
        engine = build_engine(database_url)
        try:
            await SqlWorkflowDefinitionCatalog(engine).register(
                definition=_minimal_workflow_definition(), pack_id=_PACK_ID
            )
            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="voice-route-test-principal",
            )
            return instance.workflow_id
        finally:
            await engine.dispose()

    return asyncio.run(_seed())


def test_voice_intent_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post("/api/v1/voice/intent", json={"intent_type": "check_health"})

    assert response.status_code == 401


def test_a_real_check_health_intent_reaches_the_real_health_service(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The headline proof that R-018 item 5 is closed: a real HTTP
    request genuinely reaches `PlatformIntentRouter` inside the real
    running app, and comes back carrying the real `HealthService`'s own
    real readiness report — not a canned string."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/voice/intent",
            json={"intent_type": "check_health"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent_type"] == "check_health"
    assert body["platform_action"] == "HealthService.readiness()"
    # The real report travelled through, rather than being summarised
    # away: the spoken text names the same status the raw report carries.
    assert body["raw_response"]["status"] in body["response_text"]


def test_a_real_get_workflow_status_intent_reads_a_real_instance(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The router reaches the real `WorkflowInstanceRepository` that
    `bootstrap` put on `app.state` — proving the wiring, not just the
    route."""
    workflow_id = _seed_real_instance(database_url)

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/voice/intent",
            json={"intent_type": "get_workflow_status", "workflow_id": workflow_id},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent_type"] == "get_workflow_status"
    assert body["raw_response"]["workflow_id"] == workflow_id


def test_a_missing_required_slot_is_refused_rather_than_guessed(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`get_workflow_status` without a `workflow_id` has no sensible
    default; the router already raises `VoiceIntentError` for it and the
    route must surface that as a real 4xx rather than a 500."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/voice/intent",
            json={"intent_type": "get_workflow_status"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 400


def test_an_unknown_intent_type_is_rejected_by_the_real_contract(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`VoiceIntentType` is a real closed `Literal`, so an invented
    intent is refused by the model itself — the route never has to
    maintain a second, drifting list of valid intents."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/voice/intent",
            json={"intent_type": "launch_the_missiles"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 422
