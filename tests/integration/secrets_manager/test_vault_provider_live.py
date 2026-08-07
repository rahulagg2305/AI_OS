"""Real, self-hosted-Vault-backed proof of the ``vault`` secret backend
(``P07-S02-M19-T01``, ADR-0024's own "reference production backend") —
mirrors the OIDC ticket's own "real, self-hosted JWKS HTTP server, not
a mock" precedent (``P07-S02-M14-T01``).

A real Vault dev-mode container (``tests/integration/_vault_fixture.py``)
auto-unseals and mounts a real KV v2 engine at ``secret/`` — this file
writes into it over Vault's own real HTTP API (raw ``httpx``, the
identical client this codebase's own ``VaultSecretProvider`` uses; no
``hvac`` dependency introduced anywhere in this codebase) and reads it
back only through the real, production code path:
``VaultSecretProvider``/``build_secret_provider_from_env``.
"""

from __future__ import annotations

from collections.abc import Generator

import httpx
import pytest

from ai_os_kernel.secrets_manager.backend_selection import (
    build_secret_provider_from_env,
    secret_reference_for,
)
from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.vault_provider import (
    VaultSecretProvider,
    build_vault_secret_provider,
)
from tests.integration._vault_fixture import _ROOT_TOKEN, vault_container


@pytest.fixture(scope="module")
def vault_address() -> Generator[str, None, None]:
    with vault_container() as container:
        yield container.get_connection_url()


def _write_kv2(address: str, path: str, data: dict[str, str]) -> None:
    """Writes a real KV v2 secret via Vault's own HTTP API — every
    write creates a new, real version, exactly as ``vault kv put``
    would."""
    response = httpx.post(
        f"{address}/v1/secret/data/{path}",
        json={"data": data},
        headers={"X-Vault-Token": _ROOT_TOKEN},
    )
    response.raise_for_status()


async def test_resolves_a_real_secret_written_through_vaults_own_api(vault_address: str) -> None:
    _write_kv2(vault_address, "llm/anthropic-api-key", {"api_key": "sk-real-vault-value"})
    provider = build_vault_secret_provider(address=vault_address, token=_ROOT_TOKEN)

    secret = await provider.resolve("secret://vault/llm/anthropic-api-key")

    assert secret.reveal() == "sk-real-vault-value"


async def test_real_kv_v2_versioning_resolves_each_version_independently(
    vault_address: str,
) -> None:
    _write_kv2(vault_address, "rotating/db-password", {"password": "first-real-value"})
    _write_kv2(vault_address, "rotating/db-password", {"password": "second-real-value"})
    provider = build_vault_secret_provider(address=vault_address, token=_ROOT_TOKEN)

    current = await provider.resolve("secret://vault/rotating/db-password")
    first_version = await provider.resolve("secret://vault/rotating/db-password#1")
    second_version = await provider.resolve("secret://vault/rotating/db-password#2")

    assert current.reveal() == "second-real-value"
    assert first_version.reveal() == "first-real-value"
    assert second_version.reveal() == "second-real-value"


async def test_a_genuinely_nonexistent_path_is_refused(vault_address: str) -> None:
    provider = build_vault_secret_provider(address=vault_address, token=_ROOT_TOKEN)

    with pytest.raises(SecretResolutionError, match="does not exist"):
        await provider.resolve("secret://vault/never/written")


async def test_an_invalid_token_is_refused(vault_address: str) -> None:
    _write_kv2(vault_address, "restricted/key", {"value": "should-not-be-readable"})
    provider = build_vault_secret_provider(address=vault_address, token="not-a-real-token")  # noqa: S106

    with pytest.raises(SecretResolutionError):
        await provider.resolve("secret://vault/restricted/key")


async def test_the_real_backend_switch_selects_and_resolves_against_this_real_vault(
    vault_address: str,
) -> None:
    """The design-fork proof, against genuine infrastructure rather
    than logic alone: the same ``env`` mapping that makes
    ``build_secret_provider_from_env`` construct a real
    ``VaultSecretProvider`` also makes ``secret_reference_for`` build a
    ``vault://`` reference — and that reference genuinely resolves
    against this real container."""
    _write_kv2(vault_address, "security/jwt-signing-key", {"key": "real-signing-material"})
    env = {
        "AIOS_SECRET_BACKEND": "vault",
        "AIOS_VAULT_ADDR": vault_address,
        "AIOS_VAULT_TOKEN": _ROOT_TOKEN,
    }

    provider = build_secret_provider_from_env(env)
    reference = secret_reference_for("security/jwt-signing-key", env)

    assert isinstance(provider, VaultSecretProvider)
    secret = await provider.resolve(reference)
    assert secret.reveal() == "real-signing-material"
