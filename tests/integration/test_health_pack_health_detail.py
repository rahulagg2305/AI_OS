"""Real, end-to-end proof of this step's own deliverable:
``manifest_loader_check`` now surfaces the Pack Health Collector's own
real ``catalog.packs.health`` snapshot in ``/health/ready``'s reported
response — not just activation state.

Two real scenarios:

1. The real Software Engineering pack, discovered and activated through
   the real, zero-manual-intervention startup path (the prior two
   steps' own real composition, exercised unmodified here) — `_lifespan`
   genuinely polls it once via the real, Echo-backed health-check
   registry (no live Anthropic credential needed), and the full health
   detail (status, real consecutive-failure count against the real
   threshold, a real ``checked_at`` timestamp) is genuinely visible in
   `/health/ready`'s own response for a pack that is, in fact, healthy.
2. A minimal synthetic pack with one agent whose own ``entrypoint`` is a
   real, genuinely unimportable dotted path — started twice, as two
   real, separate Kernel "restarts" against the same database, each of
   which genuinely polls once via `_lifespan`'s own real wiring,
   accumulating real, observed ``consecutive_failures`` to 2 — still
   below `CONSECUTIVE_FAILURE_THRESHOLD` (3), so the pack itself stays
   genuinely `ACTIVATED`, not yet `FAILED`. `/health/ready`, read within
   that same second startup's own session, genuinely reports this as
   `degraded` — the real "early warning before the pack actually goes
   down" this step exists to add — naming the specific failing agent
   and the real, non-zero consecutive-failure count.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.capability_manager.health_poller import CONSECUTIVE_FAILURE_THRESHOLD
from ai_os_kernel.configuration_manager import PlatformConfig
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

_FLAKY_PACK_ID = "health-detail-flaky-pack"
_FLAKY_AGENT_ID = f"{_FLAKY_PACK_ID}/flaky-agent"


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


def _config(pack_dir: Path | None = None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[str(pack_dir)] if pack_dir is not None else ["capability_packs"],
        manifest_schema_path=SCHEMA_PATH,
    )


def _write_flaky_pack_manifest(pack_root: Path) -> None:
    """A minimal, schema-valid manifest declaring one agent whose own
    ``entrypoint`` is a real, genuinely unimportable dotted path — the
    identical, already-proven "not a mock, a real
    ``EntrypointLoadError``" scenario
    ``tests/integration/capability_manager/test_health_poller.py``
    already established, this time discovered through the real
    filesystem-scan path (``manifest_loader.scan()``), not a hand-built
    Python dict."""
    pack_root.mkdir(parents=True, exist_ok=True)
    (pack_root / "manifest.yaml").write_text(
        f"""\
apiVersion: ai-os/v1
kind: CapabilityPack

metadata:
  id: {_FLAKY_PACK_ID}
  name: {_FLAKY_PACK_ID}
  version: 0.1.0
  description: >-
    A minimal, schema-valid manifest with one genuinely broken agent
    entrypoint, used only to prove /health/ready's own real,
    sub-threshold early-warning reporting.
  owner: platform-team
  license: UNLICENSED

compatibility:
  minKernelVersion: 0.1.0

dependencies:
  sdkVersion: ">=0.1.0,<1.0.0"

entryPoint: ai_os_pack_software_engineering.pack:SoftwareEngineeringPack

agents:
  - id: flaky-agent
    name: Flaky Agent
    version: 0.1.0
    purpose: Deliberately unresolvable, for real health-check proof.
    entrypoint: ai_os_pack_software_engineering.agents.does_not_exist:NoSuchEntrypoint
    inputSchema: ai_os_pack_software_engineering.agents.verification:TestAgentOutput
    outputSchema: ai_os_pack_software_engineering.agents.verification:TestAgentOutput
""",
        encoding="utf-8",
    )


def test_health_ready_shows_full_health_detail_for_a_genuinely_healthy_pack(
    database_url: str,
) -> None:
    """No manual register()/activate()/poll call anywhere in this test —
    the real, zero-intervention startup path (prior two steps) does all
    of it, including the real poll."""
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    manifest_component = next(c for c in body["components"] if c["name"] == "manifest_loader")
    assert manifest_component["status"] == "ok"
    detail = manifest_component["detail"]
    assert "software-engineering [healthy" in detail
    assert f"consecutive_failures=0/{CONSECUTIVE_FAILURE_THRESHOLD}" in detail
    assert "checked_at=" in detail
    # Every discovered pack (including the zero-agent, capability-less
    # _template example) is genuinely healthy this run — real proof
    # that "failed_agents" only ever appears for a pack that actually
    # has one, not printed unconditionally.
    assert "failed_agents" not in detail


def test_health_ready_reports_sub_threshold_consecutive_failures_as_a_degraded_early_warning(
    database_url: str, tmp_path: Path
) -> None:
    """Two real, separate Kernel startups against the same database -
    each genuinely polls once via _lifespan's own real wiring. After
    both, consecutive_failures is genuinely 2 - still below
    CONSECUTIVE_FAILURE_THRESHOLD (3) - so the pack itself is still
    genuinely ACTIVATED, not FAILED, and /health/ready must say so as a
    real, visible early warning, not stay silent until the pack
    actually goes down."""
    packs_root = tmp_path / "packs"
    _write_flaky_pack_manifest(packs_root / _FLAKY_PACK_ID)
    config = _config(packs_root)

    with TestClient(build_app(config)):
        pass  # first real startup: register + activate + poll #1 (consecutive_failures=1)

    with TestClient(build_app(config)) as client:
        # second real startup: idempotent register/activate skip + poll
        # #2 (consecutive_failures=2) - read /health/ready inside this
        # same session, since a third startup would poll a third time
        # and cross the threshold.
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"

    manifest_component = next(c for c in body["components"] if c["name"] == "manifest_loader")
    assert manifest_component["status"] == "degraded"
    detail = manifest_component["detail"]
    assert f"{_FLAKY_PACK_ID} [unhealthy" in detail
    assert f"consecutive_failures=2/{CONSECUTIVE_FAILURE_THRESHOLD}" in detail
    assert f"failed_agents=['{_FLAKY_AGENT_ID}']" in detail
    # The real, load-bearing assertion: still ACTIVATED, not yet FAILED -
    # this is what makes it a genuine early warning rather than a
    # duplicate of the already-covered "pack failed" reporting.
    assert f"{_FLAKY_PACK_ID} [state=" not in detail
