"""Shared helper for this tree's own real, self-hosted Vault
container(s) — the identical "opt-in, clearly skipped, not a crash"
shape (ADR-0015) ``tests/integration/_postgres_fixture.py`` already
establishes for Postgres, extended here to Vault
(``P07-S02-M19-T01``).

Named with a leading underscore, and not itself a ``test_*.py``/
``conftest.py`` file, so pytest never tries to collect it as a test
module — every caller imports ``vault_container`` explicitly.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import docker.errors
import pytest
from testcontainers.community.vault import VaultContainer

_IMAGE = "hashicorp/vault:1.17"
_ROOT_TOKEN = "test-root-token"  # noqa: S105 -- a disposable dev-mode container token, never a real credential


@contextlib.contextmanager
def vault_container() -> Iterator[VaultContainer]:
    """Identical to ``VaultContainer(_IMAGE, root_token=_ROOT_TOKEN)``
    used as a context manager, except that a genuinely unreachable
    Docker daemon becomes a clean, clearly-reasoned ``pytest.skip()``
    instead of a raw exception propagating out of ``testcontainers``'
    own container-start call. Vault's own dev-mode server
    (``VAULT_DEV_ROOT_TOKEN_ID``) auto-unseals and mounts a ``secret/``
    KV v2 engine — the real default this module's own
    ``VaultSecretProvider`` also defaults to."""
    try:
        container = VaultContainer(_IMAGE, root_token=_ROOT_TOKEN)
        container.start()
    except (docker.errors.DockerException, OSError) as exc:
        pytest.skip(
            "Docker daemon is not reachable — this test's own VaultContainer "
            f"fixture is opt-in (ADR-0015): {exc}"
        )
    try:
        yield container
    finally:
        container.stop()
