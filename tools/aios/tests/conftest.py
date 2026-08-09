"""Real, locally bound Kernel server fixtures for this CLI's own tests
— builds on the shared ``tests.integration._live_kernel_fixture``
helper (the identical "real local HTTP server, real socket, real
thread" pattern this codebase already uses pervasively), extracted
there once ``capability_packs/voice_jarvis``'s own tests needed the
identical mechanism.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from tests.integration._live_kernel_fixture import start_live_kernel
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
SIGNING_KEY = "aios-cli-test-signing-key-at-least-32-bytes-long"
REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(autouse=True)
def isolated_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every real test in this package runs against a real, temporary
    config file — never the developer's own real
    ``~/.config/aios/config.toml``. Autouse: a test that forgets to ask
    for this must still never touch a real machine's real config."""
    monkeypatch.setattr("ai_os_cli.config._config_path", lambda: tmp_path / "aios" / "config.toml")


@pytest.fixture
def live_kernel_no_db(monkeypatch: pytest.MonkeyPatch) -> Generator[str, None, None]:
    """A real, running Kernel with no real database — proves this
    CLI's own behaviour against every genuine degrade path
    (401/403/503), never against a fabricated response."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    config = PlatformConfig(
        env="local", role="api", capability_pack_dirs=[], manifest_schema_path=SCHEMA_PATH
    )
    running = start_live_kernel(build_app(config))
    try:
        yield running.base_url
    finally:
        running.stop()


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


@pytest.fixture
def live_kernel_with_db(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Generator[str, None, None]:
    """A real, running Kernel against a real, migrated Postgres
    (ADR-0015 — no mocking the database) — proves this CLI's own
    behaviour against a genuinely working Capability Manager/Workflow
    Engine, not just their 503-unavailable degrade paths."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.setenv("AIOS_DATABASE_URL", database_url)
    config = PlatformConfig(
        env="local", role="api", capability_pack_dirs=[], manifest_schema_path=SCHEMA_PATH
    )
    running = start_live_kernel(build_app(config))
    try:
        yield running.base_url
    finally:
        running.stop()
