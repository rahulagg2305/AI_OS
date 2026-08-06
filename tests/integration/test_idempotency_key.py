"""Real, database-backed proof of `IdempotencyKeyMiddleware`
(`P06-S01-M36-T03`) — mirrors `test_workflows_route.py`'s own real
composition-root pattern exactly (real Postgres, real bearer tokens,
`POST /api/v1/workflows` as the one real, authenticated, mutating
route this repo already has), extended with a real `Idempotency-Key`
header.

No real Anthropic credential is used — every real POST still reaches
the real Workflow Engine and gets a real, structured `failed` outcome
(no demo agent registered), which is exactly what proves "at-most-once
*effect*", not merely "same-looking response twice": a real,
`workflow_instances` row is genuinely created (or genuinely not
created a second time) regardless of the demo agent's own absence.

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
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_instances
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "idempotency-test-signing-key-at-least-32-bytes"


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
        env="test", role="api", capability_pack_dirs=[], manifest_schema_path=SCHEMA_PATH
    )


def _token(sub: str = "idempotency-test-user") -> str:
    claims = {
        "sub": sub,
        "roles": ["operator"],
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


async def _count_workflow_instances(database_url: str) -> int:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(sa.func.count()).select_from(workflow_instances)
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


def test_a_replayed_key_with_the_identical_body_has_only_one_real_effect(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Idempotency-Key": "idem-replay-test-key",
    }

    before = asyncio.run(_count_workflow_instances(database_url))
    with TestClient(app) as client:
        first = client.post("/api/v1/workflows", json={"inputs": {}}, headers=headers)
        second = client.post("/api/v1/workflows", json={"inputs": {}}, headers=headers)
    after = asyncio.run(_count_workflow_instances(database_url))

    assert first.status_code == 200
    assert second.status_code == 200
    # The real proof: the identical, already-computed response is
    # replayed verbatim -- including the same real workflow_id, which
    # a genuine second POST would never generate on its own.
    assert first.json() == second.json()
    # At-most-once *effect*, not just a matching response: only one
    # real workflow_instances row was genuinely created.
    assert after - before == 1


def test_a_reused_key_with_a_different_body_is_refused_as_a_real_conflict(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Idempotency-Key": "idem-conflict-test-key",
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/workflows", json={"inputs": {}}, headers=headers)
        second = client.post(
            "/api/v1/workflows", json={"inputs": {"different": True}}, headers=headers
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.headers["content-type"] == "application/problem+json"
    body = second.json()
    assert body["status"] == 409
    assert "idem-conflict-test-key" in body["detail"]


def test_requests_without_an_idempotency_key_are_each_genuinely_independent(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token()}"}

    before = asyncio.run(_count_workflow_instances(database_url))
    with TestClient(app) as client:
        first = client.post("/api/v1/workflows", json={"inputs": {}}, headers=headers)
        second = client.post("/api/v1/workflows", json={"inputs": {}}, headers=headers)
    after = asyncio.run(_count_workflow_instances(database_url))

    assert first.status_code == 200
    assert second.status_code == 200
    # No Idempotency-Key at all -- genuinely two, real, distinct effects.
    assert first.json()["workflow_id"] != second.json()["workflow_id"]
    assert after - before == 2


def test_a_different_principal_reusing_the_same_key_is_also_a_real_conflict(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={
                "Authorization": f"Bearer {_token('principal-a')}",
                "Idempotency-Key": "idem-cross-principal-key",
            },
        )
        second = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={
                "Authorization": f"Bearer {_token('principal-b')}",
                "Idempotency-Key": "idem-cross-principal-key",
            },
        )

    assert first.status_code == 200
    # Real, deliberate extension beyond §9's own literal words -- see
    # idempotency.py's own module docstring for why a stored key's own
    # principal mismatching is treated identically to a body mismatch.
    assert second.status_code == 409
