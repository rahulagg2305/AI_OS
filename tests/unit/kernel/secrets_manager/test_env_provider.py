"""Unit tests for EnvSecretProvider: the env-var backend (ADR-0024:
"Environment variables | Local development only"). Uses an injected
fake mapping throughout — never the real process environment — so
these tests cannot leak into or be affected by the machine's actual
environment variables."""

import pytest

from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretResolutionError


@pytest.mark.asyncio
async def test_resolves_a_flat_name_to_the_expected_env_var() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_DATABASE_PASSWORD": "hunter2"})

    secret = await provider.resolve("secret://env/database-password")

    assert secret.reveal() == "hunter2"


@pytest.mark.asyncio
async def test_resolves_a_nested_path_name_to_the_expected_env_var() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "sk-fake-value"})

    secret = await provider.resolve("secret://env/llm/anthropic-api-key")

    assert secret.reveal() == "sk-fake-value"


@pytest.mark.asyncio
async def test_missing_env_var_is_rejected_clearly() -> None:
    provider = EnvSecretProvider(env={})

    with pytest.raises(SecretResolutionError, match="AIOS_SECRET_DATABASE_PASSWORD"):
        await provider.resolve("secret://env/database-password")


@pytest.mark.asyncio
async def test_a_reference_naming_a_different_provider_is_rejected() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_DATABASE_PASSWORD": "hunter2"})

    with pytest.raises(SecretResolutionError, match="not 'env'"):
        await provider.resolve("secret://vault/database-password")


@pytest.mark.asyncio
async def test_a_reference_requesting_a_version_is_rejected() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_DATABASE_PASSWORD": "hunter2"})

    with pytest.raises(SecretResolutionError, match="no versioning"):
        await provider.resolve("secret://env/database-password#v2")


@pytest.mark.asyncio
async def test_a_malformed_reference_is_rejected_before_any_lookup() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_DATABASE_PASSWORD": "hunter2"})

    with pytest.raises(SecretResolutionError, match="not a valid secret reference"):
        await provider.resolve("not-a-secret-reference")


@pytest.mark.asyncio
async def test_defaults_to_the_real_process_environment_when_none_is_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_SECRET_DATABASE_PASSWORD", "from-real-environment")
    provider = EnvSecretProvider()

    secret = await provider.resolve("secret://env/database-password")

    assert secret.reveal() == "from-real-environment"
