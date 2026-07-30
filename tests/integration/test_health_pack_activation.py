"""Real, end-to-end proof of this step's own deliverable: the Health
Service's ``manifest_loader_check`` now reports a discovered pack's
*real* activation status — not just whether its manifest is schema-valid
— by genuinely reading ``catalog.packs.state`` through the existing
``SqlPackLifecycleRepository.get_pack()`` accessor
(``ai_os_kernel.bootstrap._build_health_service``).

Two real scenarios, each its own manifest, its own pack id, and its own
temp pack directory (both share one module-scoped Postgres container —
independent rows, no interaction):

1. A genuinely successful Kernel startup (real discovery -> real
   registration -> real activation, the previous step's own real
   composition, exercised unmodified here) makes ``/health/ready``
   report that pack as activated and the overall status ``"ready"``.
2. A pack whose real ``catalog.packs`` row is pre-seeded (directly, via
   a raw insert — the only way to reach a state no method this codebase
   actually calls ever produces, standing in for whatever real
   operational event would genuinely leave a pack stuck) in a state
   ``activate()`` cannot transition out of (``failed``) is reported as
   ``"not activated"`` with its own real state named, and the overall
   status genuinely ``"degraded"`` — not a generic message.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.catalog_schema import packs as packs_table
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.pack_state import PackState
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_HEALTHY_PACK_ID = "health-check-healthy-pack"
_STUCK_PACK_ID = "health-check-stuck-pack"


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


def _config(pack_dir: Path) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[str(pack_dir)],
        manifest_schema_path=SCHEMA_PATH,
    )


def _write_minimal_manifest(pack_root: Path, *, pack_id: str) -> None:
    """A minimal, schema-valid, capability-less manifest — the identical
    shape ``capability_packs/_template/manifest.yaml`` already
    establishes as real and schema-valid — declaring no agents/prompts/
    tools, since this step's own tests only need a pack identity real
    enough for the health check to discover and look up, not a real
    agent to resolve."""
    pack_root.mkdir(parents=True, exist_ok=True)
    (pack_root / "manifest.yaml").write_text(
        f"""\
apiVersion: ai-os/v1
kind: CapabilityPack

metadata:
  id: {pack_id}
  name: {pack_id}
  version: 0.1.0
  description: >-
    A minimal, schema-valid, capability-less manifest used only to
    prove the Health Service's own real activation-status logic.
  owner: platform-team
  license: UNLICENSED

compatibility:
  minKernelVersion: 0.1.0

dependencies:
  sdkVersion: ">=0.1.0,<1.0.0"
""",
        encoding="utf-8",
    )


def test_health_ready_reports_a_genuinely_activated_pack_as_healthy(
    tmp_path: Path, database_url: str
) -> None:
    """No manual register()/activate() call anywhere in this test — the
    real _lifespan-driven discovery (wired in the previous step) does
    it, and this step's own new health-check logic reads the real
    result back."""
    packs_root = tmp_path / "packs"
    _write_minimal_manifest(packs_root / _HEALTHY_PACK_ID, pack_id=_HEALTHY_PACK_ID)

    app = build_app(_config(packs_root))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    manifest_component = next(c for c in body["components"] if c["name"] == "manifest_loader")
    assert manifest_component["status"] == "ok"
    assert "1 pack(s) discovered, 0 invalid" in manifest_component["detail"]
    assert "1 activated, 0 not activated" in manifest_component["detail"]


def test_health_ready_reports_a_stuck_pack_as_degraded_with_the_real_reason(
    tmp_path: Path, database_url: str
) -> None:
    """A real, deterministic 'stuck during activation' scenario: a
    catalog.packs row pre-seeded directly (bypassing register()
    entirely — the only way to reach a state no method this codebase
    actually calls ever produces) in `failed`, a state
    `activate()`'s own `_ACTIVATABLE_FROM_STATES` does not include.

    When the real Kernel starts, `_register_and_activate_discovered_packs`
    genuinely attempts both register() (rejected: PackAlreadyRegisteredError,
    the duplicate pack_id primary key) and activate() (rejected:
    InvalidPackTransitionError, since `failed` isn't activatable) — both
    real, both logged, neither crashing startup — leaving the row
    exactly as pre-seeded. The health check then reads that real,
    unchanged state back."""
    packs_root = tmp_path / "packs"
    _write_minimal_manifest(packs_root / _STUCK_PACK_ID, pack_id=_STUCK_PACK_ID)

    engine = build_engine(database_url)

    async def _seed_stuck_pack() -> None:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(packs_table).values(
                        pack_id=_STUCK_PACK_ID,
                        version="0.1.0",
                        state=PackState.FAILED.value,
                        manifest={},
                        sdk_version=">=0.1.0,<1.0.0",
                        min_kernel_version="0.1.0",
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_seed_stuck_pack())

    app = build_app(_config(packs_root))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"

    manifest_component = next(c for c in body["components"] if c["name"] == "manifest_loader")
    assert manifest_component["status"] == "degraded"
    assert "1 pack(s) discovered, 0 invalid" in manifest_component["detail"]
    assert "0 activated, 1 not activated" in manifest_component["detail"]
    assert f"{_STUCK_PACK_ID} [state=failed]" in manifest_component["detail"]
