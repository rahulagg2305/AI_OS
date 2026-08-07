"""Unit tests for the real, JWKS-based OIDC verifier
(``ai_os_kernel.security_manager.token_verifier.OidcBearerTokenVerifier``,
``P07-S02-M14-T01``).

**No mock, no stubbed HTTP client.** A real RSA keypair is generated
(``cryptography``), a real JWK document is built from the real public
key (:func:`jwt.algorithms.RSAAlgorithm.to_jwk` — the same real
encoding a genuine identity provider would publish), and served over a
real, local, ephemeral-port HTTP server
(:class:`http.server.HTTPServer`, module-scoped, one real server for
every test in this file). :class:`jwt.PyJWKClient` — the exact same
class the real verifier uses — makes a real HTTP GET against it.
Every token is signed with the real private key
(:func:`jwt.encode`, RS256) — the only thing "fake" here is that the
identity provider is self-hosted rather than a third-party SaaS, the
identical `postgres_container()` shape this codebase already uses for
"a real Postgres, just not a managed cloud one."
"""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import PrincipalType
from ai_os_kernel.security_manager.token_verifier import OidcBearerTokenVerifier

_ISSUER = "https://issuer.example.test"
_AUDIENCE = "aios-kernel"
_KID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_key_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")

_other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_other_private_key_pem = _other_private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")

_jwk = json.loads(RSAAlgorithm(RSAAlgorithm.SHA256).to_jwk(_private_key.public_key()))
_jwk["kid"] = _KID
_jwk["use"] = "sig"
_jwk["alg"] = "RS256"
_JWKS_DOCUMENT = json.dumps({"keys": [_jwk]}).encode("utf-8")


class _JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's own required name
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_JWKS_DOCUMENT)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — stdlib's own signature
        pass  # silence per-request logging; this is a real server, not a chatty one


@pytest.fixture(scope="module")
def jwks_uri() -> Generator[str, None, None]:
    server = HTTPServer(("127.0.0.1", 0), _JwksHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/jwks.json"
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def _token(
    claims: dict[str, object],
    *,
    private_key_pem: str = _private_key_pem,
    kid: str | None = _KID,
) -> str:
    headers = {"kid": kid} if kid else None
    return jwt.encode(claims, private_key_pem, algorithm="RS256", headers=headers)


def _future_claims(**extra: object) -> dict[str, object]:
    return {
        "sub": "user-1",
        "roles": ["operator"],
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        **extra,
    }


@pytest.mark.asyncio
async def test_verifies_a_real_token_against_a_real_jwks_endpoint(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)

    principal = await verifier.verify(_token(_future_claims()))

    assert principal.principal_id == "user-1"
    assert principal.principal_type is PrincipalType.USER
    assert principal.roles == frozenset({"operator"})


@pytest.mark.asyncio
async def test_a_service_account_token_is_recognised(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)

    principal = await verifier.verify(_token(_future_claims(principal_type="service_account")))

    assert principal.principal_type is PrincipalType.SERVICE_ACCOUNT


@pytest.mark.asyncio
async def test_a_token_signed_by_a_key_not_in_the_real_jwks_document_is_rejected(
    jwks_uri: str,
) -> None:
    """The real, load-bearing proof: a token signed with a *different*
    real RSA private key — one the JWKS endpoint never published — is
    genuinely rejected. `PyJWKClient` cannot even find a matching
    `kid`, since this signs with the other keypair under the same
    (only) real `kid` the server publishes."""
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    token = _token(_future_claims(), private_key_pem=_other_private_key_pem)

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_token_with_no_matching_kid_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    token = _token(_future_claims(), kid="no-such-key")

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_token_with_the_wrong_issuer_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    token = _token(_future_claims(iss="https://a-different-issuer.example.test"))

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_token_with_the_wrong_audience_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    token = _token(_future_claims(aud="a-different-audience"))

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_an_expired_token_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    expired = _token(
        {
            "sub": "user-1",
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "exp": datetime.now(UTC) - timedelta(minutes=5),
        }
    )

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify(expired)


@pytest.mark.asyncio
async def test_a_token_missing_the_sub_claim_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)
    token = _token(
        {
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
    )

    with pytest.raises(InvalidTokenError, match="sub"):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_a_malformed_token_is_rejected(jwks_uri: str) -> None:
    verifier = OidcBearerTokenVerifier(issuer=_ISSUER, audience=_AUDIENCE, jwks_uri=jwks_uri)

    with pytest.raises(InvalidTokenError, match="failed OIDC verification"):
        await verifier.verify("not-a-jwt-at-all")
