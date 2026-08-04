"""Real proof that :func:`build_redis_client` genuinely connects to a
real Redis instance and performs a real operation (ADR-0015 — no
mocking infrastructure). Uses the identical image
(``redis:7-alpine``) ``infra/docker-compose.yml`` already provisions
for the ``core``/``full`` profiles — the same "actually use the Redis
Compose already provisions" this ticket's own Goal names, run as an
isolated, real container rather than depending on a long-running
Compose stack being up, the same testcontainers-first pattern every
other real-infrastructure suite in this tree already establishes.

Docker-gated, opt-in, skipped with a clear reason when the daemon is
unreachable — the same shape
``tests/integration/sandbox/test_docker_sandbox_live.py``'s own
``docker_available`` fixture establishes. A single real caller here,
so no shared fixture module is extracted (ADR-0004) — unlike
``tests/integration/_postgres_fixture.py``'s ~30 real callers.
"""

from __future__ import annotations

from collections.abc import Generator

import docker
import docker.errors
import pytest
from testcontainers.community.redis import RedisContainer

from ai_os_kernel.caching.client import build_redis_client

_IMAGE = "redis:7-alpine"


@pytest.fixture(scope="module")
def redis_url() -> Generator[str, None, None]:
    try:
        docker.from_env().ping()
    except (docker.errors.DockerException, OSError) as exc:
        pytest.skip(f"Docker daemon is not reachable — this live-container suite is opt-in: {exc}")

    with RedisContainer(_IMAGE) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


async def test_build_redis_client_genuinely_connects_to_a_real_redis(redis_url: str) -> None:
    client = build_redis_client(redis_url)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()


async def test_build_redis_client_genuinely_sets_and_gets_a_real_key(redis_url: str) -> None:
    client = build_redis_client(redis_url)
    try:
        assert await client.set("aios:test:key", "real-value") is True
        assert await client.get("aios:test:key") == "real-value"
    finally:
        await client.delete("aios:test:key")
        await client.aclose()
