"""Smoke test proving the Kernel API entrypoint starts and responds, end
to end through the real composition root (bootstrap.build_app), with
real configuration and manifest-loader wiring.

Unit-level per docs/10_testing/test_strategy.md: in-process ASGI calls
only, no real network, no real database.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"


def _config(**overrides: object) -> PlatformConfig:
    defaults: dict[str, object] = {
        "env": "test",
        "role": "api",
        "capability_pack_dirs": [],  # isolated from the real capability_packs/ tree
        "manifest_schema_path": SCHEMA_PATH,
    }
    defaults.update(overrides)
    return PlatformConfig(**defaults)


def _client(config: PlatformConfig | None = None) -> TestClient:
    return TestClient(build_app(config or _config()))


def test_health_live_reports_status_without_dependencies() -> None:
    response = _client().get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_health_ready_reports_component_statuses() -> None:
    response = _client().get("/api/v1/health/ready")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ready"
    names = {c["name"] for c in body["components"]}
    assert names == {"configuration_manager", "manifest_loader"}


def test_health_ready_is_degraded_when_a_discovered_pack_is_invalid(tmp_path: Path) -> None:
    pack_dir = tmp_path / "broken-pack"
    pack_dir.mkdir()
    (pack_dir / "manifest.yaml").write_text(
        "apiVersion: ai-os/v1\nkind: CapabilityPack\n", encoding="utf-8"
    )

    config = _config(capability_pack_dirs=[str(tmp_path)])
    response = _client(config).get("/api/v1/health/ready")

    body = response.json()
    assert body["status"] == "degraded"
    manifest_component = next(c for c in body["components"] if c["name"] == "manifest_loader")
    assert "1 invalid" in manifest_component["detail"]


def test_version_reports_configured_environment_and_role() -> None:
    response = _client().get("/api/v1/version")
    assert response.status_code == 200

    body = response.json()
    assert body["service"] == "ai-os-kernel"
    assert body["environment"] == "test"
    assert body["role"] == "api"
    assert "version" in body


def test_settings_are_environment_driven_not_hardcoded() -> None:
    """No hard-coded values (non-negotiable rule): changing configuration
    must change the response, proving the value flows from config."""
    default_body = _client().get("/api/v1/version").json()
    other_body = _client(_config(env="staging", role="worker")).get("/api/v1/version").json()

    assert default_body["environment"] != other_body["environment"]
    assert other_body["environment"] == "staging"
    assert other_body["role"] == "worker"


def test_response_carries_a_generated_trace_id_header() -> None:
    response = _client().get("/api/v1/health/live")

    assert "x-trace-id" in {k.lower() for k in response.headers}
    assert len(response.headers["X-Trace-Id"]) > 0


def test_incoming_trace_id_is_honored() -> None:
    response = _client().get("/api/v1/health/live", headers={"X-Trace-Id": "my-custom-trace"})

    assert response.headers["X-Trace-Id"] == "my-custom-trace"
