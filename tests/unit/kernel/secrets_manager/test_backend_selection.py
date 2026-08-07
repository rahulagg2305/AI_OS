"""Unit tests for the real ``AIOS_SECRET_BACKEND`` switch
(``P07-S02-M19-T01``) — secrets_management.md §5's own documented
mechanism, previously entirely unbuilt (every real caller hardcoded
``EnvSecretProvider()``). Uses an injected ``env`` mapping throughout —
never real process state — matching every other provider's own test
convention in this module.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.secrets_manager.backend_selection import (
    build_secret_provider_from_env,
    secret_reference_for,
)
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretBackendConfigError
from ai_os_kernel.secrets_manager.vault_provider import VaultSecretProvider


def test_no_backend_configured_returns_the_env_provider() -> None:
    provider = build_secret_provider_from_env({})

    assert isinstance(provider, EnvSecretProvider)


def test_backend_explicitly_env_returns_the_env_provider() -> None:
    provider = build_secret_provider_from_env({"AIOS_SECRET_BACKEND": "env"})

    assert isinstance(provider, EnvSecretProvider)


def test_backend_vault_with_full_config_returns_a_real_vault_provider() -> None:
    provider = build_secret_provider_from_env(
        {
            "AIOS_SECRET_BACKEND": "vault",
            "AIOS_VAULT_ADDR": "http://127.0.0.1:8200",
            "AIOS_VAULT_TOKEN": "s.real-token",
        }
    )

    assert isinstance(provider, VaultSecretProvider)
    assert provider._mount == "secret"


def test_backend_vault_honors_a_configured_mount() -> None:
    provider = build_secret_provider_from_env(
        {
            "AIOS_SECRET_BACKEND": "vault",
            "AIOS_VAULT_ADDR": "http://127.0.0.1:8200",
            "AIOS_VAULT_TOKEN": "s.real-token",
            "AIOS_VAULT_KV_MOUNT": "kv",
        }
    )

    assert isinstance(provider, VaultSecretProvider)
    assert provider._mount == "kv"


def test_backend_vault_missing_address_is_refused() -> None:
    with pytest.raises(SecretBackendConfigError, match="AIOS_VAULT_ADDR"):
        build_secret_provider_from_env(
            {"AIOS_SECRET_BACKEND": "vault", "AIOS_VAULT_TOKEN": "s.real-token"}
        )


def test_backend_vault_missing_token_is_refused() -> None:
    with pytest.raises(SecretBackendConfigError, match="AIOS_VAULT_TOKEN"):
        build_secret_provider_from_env(
            {"AIOS_SECRET_BACKEND": "vault", "AIOS_VAULT_ADDR": "http://127.0.0.1:8200"}
        )


def test_an_unrecognized_backend_is_refused() -> None:
    with pytest.raises(SecretBackendConfigError, match="not a real backend"):
        build_secret_provider_from_env({"AIOS_SECRET_BACKEND": "aws"})


def test_secret_reference_for_defaults_to_env() -> None:
    assert secret_reference_for("llm/anthropic-api-key", {}) == "secret://env/llm/anthropic-api-key"


def test_secret_reference_for_follows_the_configured_backend() -> None:
    reference = secret_reference_for("llm/anthropic-api-key", {"AIOS_SECRET_BACKEND": "vault"})

    assert reference == "secret://vault/llm/anthropic-api-key"


def test_secret_reference_for_and_the_provider_factory_never_disagree() -> None:
    """The real proof this design fork was closed correctly: whichever
    backend the provider factory selects is exactly the backend the
    reference names, for the identical ``env``."""
    env = {
        "AIOS_SECRET_BACKEND": "vault",
        "AIOS_VAULT_ADDR": "http://127.0.0.1:8200",
        "AIOS_VAULT_TOKEN": "s.real-token",
    }

    provider = build_secret_provider_from_env(env)
    reference = secret_reference_for("llm/anthropic-api-key", env)

    assert isinstance(provider, VaultSecretProvider)
    assert reference.startswith("secret://vault/")
