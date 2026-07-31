"""Unit tests for :func:`resolve_secret_references` against the real,
already-proven :class:`EnvSecretProvider` — no fake provider, exactly
"reuse the existing secrets_manager" this Task requires. No database
is involved at any point in this layer."""

import asyncio

import pytest

from ai_os_kernel.configuration_manager.secrets import resolve_secret_references
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretResolutionError


def test_a_top_level_secret_reference_resolves_to_the_real_value() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_LLM_API_KEY": "sk-real-value"})

    resolved = asyncio.run(
        resolve_secret_references({"api_key": "secret://env/llm-api-key"}, provider)
    )

    assert resolved["api_key"].reveal() == "sk-real-value"


def test_a_resolved_value_redacts_on_str_and_repr() -> None:
    """The one property that matters most for "never logged": even if
    something later does `str(config)` or logs the object directly, the
    real value cannot appear."""
    provider = EnvSecretProvider(env={"AIOS_SECRET_LLM_API_KEY": "sk-real-value"})

    resolved = asyncio.run(
        resolve_secret_references({"api_key": "secret://env/llm-api-key"}, provider)
    )

    assert str(resolved["api_key"]) == "***"
    assert "sk-real-value" not in repr(resolved["api_key"])


def test_a_nested_secret_reference_resolves_too() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_DB_PASSWORD": "hunter2"})

    resolved = asyncio.run(
        resolve_secret_references({"database": {"password": "secret://env/db-password"}}, provider)
    )

    assert resolved["database"]["password"].reveal() == "hunter2"


def test_non_secret_values_pass_through_unchanged() -> None:
    provider = EnvSecretProvider(env={})

    resolved = asyncio.run(
        resolve_secret_references({"host": "127.0.0.1", "port": 8000, "flag": True}, provider)
    )

    assert resolved == {"host": "127.0.0.1", "port": 8000, "flag": True}


def test_a_string_that_merely_contains_the_secret_prefix_midway_is_left_alone() -> None:
    provider = EnvSecretProvider(env={})

    resolved = asyncio.run(
        resolve_secret_references({"note": "see secret://env/x for details"}, provider)
    )

    assert resolved["note"] == "see secret://env/x for details"


def test_an_unresolvable_reference_raises_rather_than_silently_passing() -> None:
    provider = EnvSecretProvider(env={})

    with pytest.raises(SecretResolutionError):
        asyncio.run(resolve_secret_references({"api_key": "secret://env/missing"}, provider))


def test_an_empty_mapping_resolves_to_an_empty_mapping() -> None:
    provider = EnvSecretProvider(env={})

    assert asyncio.run(resolve_secret_references({}, provider)) == {}
