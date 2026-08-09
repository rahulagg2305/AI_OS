"""Real, locally bound Kernel server fixtures for this CLI's own tests
— the identical "real local HTTP server, real socket, real thread"
pattern this codebase already uses pervasively (e.g.
``ai_os_kernel``'s own webhook/notification tests), using ``uvicorn``
instead of ``http.server`` since the real target here is the real
Kernel ASGI app, not a hand-written handler.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


class _RunningServer:
    def __init__(self, base_url: str, server: uvicorn.Server, thread: threading.Thread) -> None:
        self.base_url = base_url
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


def _start_server(config: PlatformConfig) -> _RunningServer:
    app = build_app(config)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    return _RunningServer(f"http://127.0.0.1:{port}", server, thread)


@pytest.fixture
def live_kernel_no_db(monkeypatch: pytest.MonkeyPatch) -> Generator[str, None, None]:
    """A real, running Kernel with no real database — proves this
    CLI's own behaviour against every genuine degrade path
    (401/403/503), never against a fabricated response."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    running = _start_server(
        PlatformConfig(
            env="local", role="api", capability_pack_dirs=[], manifest_schema_path=SCHEMA_PATH
        )
    )
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
    running = _start_server(
        PlatformConfig(
            env="local", role="api", capability_pack_dirs=[], manifest_schema_path=SCHEMA_PATH
        )
    )
    try:
        yield running.base_url
    finally:
        running.stop()
