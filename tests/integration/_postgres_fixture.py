"""Shared helper for this tree's own ~30 independent `database_url`
fixtures (ADR-0004: a real, current, thirty-times-repeated use is
exactly the case that justifies a shared helper, unlike the
"no shared module for a single real caller each" reasoning applied
elsewhere in this codebase). Every one of those fixtures constructs a
`PostgresContainer` with the identical image/driver; the only thing
this module changes is turning a raw `docker.errors.DockerException`
(when the daemon is not reachable) into a clean `pytest.skip()` with a
clear reason — the same "opt-in, clearly skipped, not a crash" shape
(ADR-0015) `tests/integration/sandbox/test_docker_sandbox_live.py`'s
own `docker_available` fixture already established for a Docker-gated
suite, extended here to this tree's much more numerous Postgres-gated
ones.

Named with a leading underscore, and not itself a `test_*.py`/
`conftest.py` file, so pytest never tries to collect it as a test
module or treat it as fixture-discovery magic — every caller imports
`postgres_container` explicitly.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import docker.errors
import pytest
from testcontainers.community.postgres import PostgresContainer

_IMAGE = "pgvector/pgvector:pg16"
_DRIVER = "asyncpg"


@contextlib.contextmanager
def postgres_container() -> Iterator[PostgresContainer]:
    """Identical to ``PostgresContainer(_IMAGE, driver=_DRIVER)`` used
    as a context manager, except that a genuinely unreachable Docker
    daemon becomes a clean, clearly-reasoned ``pytest.skip()`` instead
    of a raw ``docker.errors.DockerException`` propagating out of
    ``testcontainers``' own container-start call."""
    try:
        container = PostgresContainer(_IMAGE, driver=_DRIVER)
        container.start()
    except (docker.errors.DockerException, OSError) as exc:
        # `OSError` as well as `DockerException` (widened 2026-07-31,
        # Phase R2 — the inconsistency the Phase R1 audit found between
        # this guard and `test_docker_sandbox_live.py`'s own, which
        # already caught both). A failure to *establish* the connection
        # — refused, unreachable, DNS failure; `TimeoutError` is itself
        # an `OSError` subclass — surfaces as the driver's own raw
        # exception rather than a wrapped `DockerException`, so the
        # narrower catch could let a genuinely-absent daemon error the
        # suite instead of skipping it. Same root cause as the
        # `registry.py` widening of the same date.
        pytest.skip(
            "Docker daemon is not reachable — this test's own PostgresContainer "
            f"fixture is opt-in (ADR-0015): {exc}"
        )
    try:
        yield container
    finally:
        container.stop()
