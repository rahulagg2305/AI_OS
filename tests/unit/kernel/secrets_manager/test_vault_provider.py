"""Unit tests for VaultSecretProvider (``P07-S02-M19-T01``) — pure
request/response-shaping logic against an ``httpx.MockTransport``
(a real, first-class ``httpx`` testing mechanism, not a hand-rolled
fake of this class's own logic). The real proof against a genuine,
self-hosted Vault server lives in
``tests/integration/secrets_manager/test_vault_provider_live.py``,
mirroring the OIDC ticket's own "unit-test the shaping, integration-test
the real server" split.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.vault_provider import (
    VaultSecretProvider,
    build_vault_secret_provider,
)


def _provider(
    handler: Callable[[httpx.Request], httpx.Response], *, mount: str = "secret"
) -> VaultSecretProvider:
    client = httpx.AsyncClient(
        base_url="http://vault.invalid", transport=httpx.MockTransport(handler)
    )
    return VaultSecretProvider(client=client, mount=mount)


def _kv2_response(data: dict[str, str]) -> httpx.Response:
    return httpx.Response(200, json={"data": {"data": data, "metadata": {"version": 1}}})


async def test_resolves_a_single_field_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/secret/data/llm/anthropic-api-key"
        assert "version" not in request.url.params
        return _kv2_response({"api_key": "sk-real-value"})

    provider = _provider(handler)

    secret = await provider.resolve("secret://vault/llm/anthropic-api-key")

    assert secret.reveal() == "sk-real-value"


async def test_uses_the_configured_mount() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/kv/data/db-password"
        return _kv2_response({"password": "hunter2"})

    provider = _provider(handler, mount="kv")

    secret = await provider.resolve("secret://vault/db-password")

    assert secret.reveal() == "hunter2"


async def test_a_version_segment_is_forwarded_as_a_query_parameter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["version"] == "3"
        return _kv2_response({"value": "old-value"})

    provider = _provider(handler)

    secret = await provider.resolve("secret://vault/rotating-secret#3")

    assert secret.reveal() == "old-value"


async def test_a_non_numeric_version_is_refused_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not make a real request for an invalid version")

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="non-negative integer"):
        await provider.resolve("secret://vault/thing#latest")


async def test_a_reference_naming_a_different_provider_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not make a real request for the wrong provider")

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="not 'vault'"):
        await provider.resolve("secret://env/llm/anthropic-api-key")


async def test_a_missing_path_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": []})

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="does not exist"):
        await provider.resolve("secret://vault/does/not/exist")


async def test_a_permission_denied_response_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": ["permission denied"]})

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="403"):
        await provider.resolve("secret://vault/restricted")


async def test_an_unreachable_vault_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="unreachable"):
        await provider.resolve("secret://vault/thing")


async def test_a_secret_with_two_fields_is_refused_as_ambiguous() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _kv2_response({"username": "admin", "password": "hunter2"})

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="exactly one field"):
        await provider.resolve("secret://vault/db-creds")


async def test_a_secret_with_no_fields_is_refused_as_ambiguous() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _kv2_response({})

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="exactly one field"):
        await provider.resolve("secret://vault/empty")


async def test_a_non_string_field_value_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"data": {"count": 5}, "metadata": {}}})

    provider = _provider(handler)

    with pytest.raises(SecretResolutionError, match="not a string"):
        await provider.resolve("secret://vault/numeric")


def test_build_vault_secret_provider_configures_the_client() -> None:
    provider = build_vault_secret_provider(
        address="http://127.0.0.1:8200",
        token="s.real-token",  # noqa: S106 — a fake, disposable test token
        mount="secret",
    )

    assert str(provider._client.base_url) == "http://127.0.0.1:8200"
    assert provider._client.headers["X-Vault-Token"] == "s.real-token"
    assert provider._mount == "secret"
