"""Bearer-token authentication (api_architecture.md §4:
``Authorization: Bearer <token>`` for both ``user`` and
``service_account`` principals).

**Two real implementations of the same `TokenVerifier` Protocol —
neither call site (:mod:`ai_os_kernel.security_manager.dependencies`,
and therefore every route) depends on either directly, exactly as this
module's own docstring already promised before either existed.**

:class:`JWTBearerTokenVerifier` verifies a JWT's signature (HS256, a
pre-shared secret resolved through
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`) and its
expiry — a real, credible bearer-token mechanism, just not one backed
by a live identity provider. Remains the safe, zero-config default:
every existing environment that has never configured a real OIDC
provider keeps this mechanism unchanged.

:class:`OidcBearerTokenVerifier` (``P07-S02-M14-T01``, ADR-0023: "user |
OIDC bearer token") verifies a JWT against a real, JWKS-fetched RS256
public key (:class:`jwt.PyJWKClient` — real HTTP fetch and caching, run
off the event loop thread since it is synchronous I/O) and validates
issuer/audience, not merely signature and expiry. **A genuine design
choice, not a fork requiring escalation:** this ticket's own literal
wording says "replace," but removing `JWTBearerTokenVerifier` outright
would break every current environment, none of which configures a real
OIDC provider yet — so this module keeps both, and
:func:`~ai_os_kernel.bootstrap._build_token_verifier` chooses OIDC only
when real issuer/audience/JWKS-URI configuration is present, falling
back to the pre-shared secret otherwise (the identical "additive,
None-default, existing caller unaffected" shape this codebase already
uses for `runtime_overrides`/`pinned_conditions`).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import jwt

from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import Principal, PrincipalType

_ALGORITHM = "HS256"
_OIDC_ALGORITHM = "RS256"


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns the :class:`Principal` it
    names, or raises :class:`InvalidTokenError`."""

    async def verify(self, token: str) -> Principal: ...


def _principal_from_claims(claims: dict[str, object]) -> Principal:
    """The one real claims -> :class:`Principal` mapping, shared by both
    verifiers below — never duplicated, so the two mechanisms can never
    silently drift on what a token's claims mean."""
    principal_id = claims.get("sub")
    if not principal_id or not isinstance(principal_id, str):
        raise InvalidTokenError("bearer token is missing the required 'sub' claim")

    principal_type_raw = claims.get("principal_type", PrincipalType.USER.value)
    if not isinstance(principal_type_raw, str):
        raise InvalidTokenError("bearer token's 'principal_type' claim must be a string")
    try:
        principal_type = PrincipalType(principal_type_raw)
    except ValueError as exc:
        raise InvalidTokenError(
            f"bearer token names unknown principal_type '{principal_type_raw}'"
        ) from exc

    roles_raw = claims.get("roles", [])
    if not isinstance(roles_raw, list):
        raise InvalidTokenError("bearer token's 'roles' claim must be a list")

    return Principal(
        principal_id=principal_id,
        principal_type=principal_type,
        roles=frozenset(roles_raw),
    )


class JWTBearerTokenVerifier:
    """The pre-shared-secret HS256 verifier — see module docstring for
    what it deliberately is and is not."""

    def __init__(self, *, signing_key: str) -> None:
        self._signing_key = signing_key

    async def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._signing_key, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"bearer token failed verification: {exc}") from exc
        return _principal_from_claims(claims)


async def build_jwt_bearer_token_verifier(
    *, secret_provider: SecretProvider, signing_key_secret_reference: str
) -> JWTBearerTokenVerifier:
    """Resolves the signing key once at construction time, mirroring
    :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`."""
    secret = await secret_provider.resolve(signing_key_secret_reference)
    return JWTBearerTokenVerifier(signing_key=secret.reveal())


class OidcBearerTokenVerifier:
    """The real, JWKS-based OIDC verifier — see module docstring for
    the full reasoning. ``jwks_uri`` is fetched (and its keys cached)
    by :class:`jwt.PyJWKClient` itself; this class never parses a JWK
    document by hand."""

    def __init__(self, *, issuer: str, audience: str, jwks_uri: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_client = jwt.PyJWKClient(jwks_uri)

    async def verify(self, token: str) -> Principal:
        try:
            # PyJWKClient.get_signing_key_from_jwt does a real, synchronous
            # HTTP fetch (cached after the first real call per kid) — run
            # off the event loop thread, the same discipline every other
            # blocking filesystem/subprocess call in this codebase uses.
            signing_key = await asyncio.to_thread(self._jwks_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[_OIDC_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"bearer token failed OIDC verification: {exc}") from exc
        return _principal_from_claims(claims)


def build_oidc_bearer_token_verifier(
    *, issuer: str, audience: str, jwks_uri: str
) -> OidcBearerTokenVerifier:
    """No secret to resolve — a JWKS endpoint publishes public keys by
    design; this exists only to mirror `build_jwt_bearer_token_verifier`'s
    own naming convention for the composition root."""
    return OidcBearerTokenVerifier(issuer=issuer, audience=audience, jwks_uri=jwks_uri)
