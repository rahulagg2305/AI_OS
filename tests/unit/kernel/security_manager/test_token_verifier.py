"""Unit tests for the minimal bearer-token authenticator
(ai_os_kernel.security_manager.token_verifier) — a pre-shared-secret
HS256 JWT verifier, deliberately not full OIDC (see that module's own
docstring). No network, no database: every token here is minted
in-process with the same secret the verifier holds.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import PrincipalType
from ai_os_kernel.security_manager.token_verifier import (
    JWTBearerTokenVerifier,
    build_jwt_bearer_token_verifier,
)

_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"


def _token(claims: dict[str, object], *, signing_key: str = _SIGNING_KEY) -> str:
    return jwt.encode(claims, signing_key, algorithm="HS256")


def _future_claims(**extra: object) -> dict[str, object]:
    return {
        "sub": "user-1",
        "roles": ["operator"],
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        **extra,
    }


@pytest.mark.asyncio
async def test_verifies_a_well_formed_token_and_extracts_the_principal() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)

    principal = await verifier.verify(_token(_future_claims()))

    assert principal.principal_id == "user-1"
    assert principal.principal_type is PrincipalType.USER
    assert principal.roles == frozenset({"operator"})


@pytest.mark.asyncio
async def test_principal_type_defaults_to_user_when_absent() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    claims = _future_claims()

    principal = await verifier.verify(_token(claims))

    assert principal.principal_type is PrincipalType.USER


@pytest.mark.asyncio
async def test_a_service_account_token_is_recognised() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)

    principal = await verifier.verify(_token(_future_claims(principal_type="service_account")))

    assert principal.principal_type is PrincipalType.SERVICE_ACCOUNT


@pytest.mark.asyncio
async def test_a_token_signed_with_the_wrong_key_is_rejected() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    token = _token(_future_claims(), signing_key="a-completely-different-signing-key")

    with pytest.raises(InvalidTokenError, match="failed verification"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_an_expired_token_is_rejected() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    expired = _token({"sub": "user-1", "exp": datetime.now(UTC) - timedelta(minutes=5)})

    with pytest.raises(InvalidTokenError, match="failed verification"):
        await verifier.verify(expired)


@pytest.mark.asyncio
async def test_a_token_missing_the_sub_claim_is_rejected() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    token = _token({"roles": ["operator"], "exp": datetime.now(UTC) + timedelta(minutes=5)})

    with pytest.raises(InvalidTokenError, match="sub"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_token_naming_an_unknown_principal_type_is_rejected() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    token = _token(_future_claims(principal_type="agent"))

    with pytest.raises(InvalidTokenError, match="unknown principal_type"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_token_with_no_roles_claim_grants_no_roles() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)
    token = _token({"sub": "user-1", "exp": datetime.now(UTC) + timedelta(minutes=5)})

    principal = await verifier.verify(token)

    assert principal.roles == frozenset()


@pytest.mark.asyncio
async def test_a_malformed_token_is_rejected() -> None:
    verifier = JWTBearerTokenVerifier(signing_key=_SIGNING_KEY)

    with pytest.raises(InvalidTokenError, match="failed verification"):
        await verifier.verify("not-a-jwt-at-all")


@pytest.mark.asyncio
async def test_build_resolves_the_signing_key_through_the_secrets_seam() -> None:
    provider = EnvSecretProvider(env={"AIOS_SECRET_SECURITY_JWT_SIGNING_KEY": _SIGNING_KEY})

    verifier = await build_jwt_bearer_token_verifier(
        secret_provider=provider,
        signing_key_secret_reference="secret://env/security/jwt-signing-key",  # noqa: S106 — a reference URI, not a credential
    )

    principal = await verifier.verify(_token(_future_claims()))
    assert principal.principal_id == "user-1"
