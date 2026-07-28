"""Bearer-token authentication (api_architecture.md §4:
``Authorization: Bearer <token>`` for both ``user`` and
``service_account`` principals).

**Deliberately not full OIDC.** ADR-0023 documents OIDC bearer tokens
for users; full OIDC needs issuer discovery, JWKS fetch and rotation,
and audience validation against a live identity provider — none of
which exist in this codebase, and standing one up is its own step, not
this one. :class:`JWTBearerTokenVerifier` verifies a JWT's signature
(HS256, a pre-shared secret resolved through
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider` — the
same "never hardcode, resolve through the existing secrets seam"
pattern :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`
already uses) and its expiry — a real, credible bearer-token mechanism,
just not one backed by a live identity provider yet.

This is the "clean minimal auth boundary that does not violate the
architecture and can later be replaced by full OIDC without rewriting
callers" this step's own approved framing anticipated: every caller
(:mod:`ai_os_kernel.security_manager.dependencies`, and therefore every
route) depends on the :class:`TokenVerifier` ``Protocol``, not on
:class:`JWTBearerTokenVerifier` directly. Swapping in a real
OIDC-backed implementation later (verifying against a JWKS endpoint,
checking issuer and audience) replaces this one class, not any call
site.
"""

from __future__ import annotations

from typing import Protocol

import jwt

from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import Principal, PrincipalType

_ALGORITHM = "HS256"


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns the :class:`Principal` it
    names, or raises :class:`InvalidTokenError`."""

    async def verify(self, token: str) -> Principal: ...


class JWTBearerTokenVerifier:
    """The one real implementation at this stage — see module docstring
    for what it deliberately is and is not."""

    def __init__(self, *, signing_key: str) -> None:
        self._signing_key = signing_key

    async def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._signing_key, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"bearer token failed verification: {exc}") from exc

        principal_id = claims.get("sub")
        if not principal_id:
            raise InvalidTokenError("bearer token is missing the required 'sub' claim")

        principal_type_raw = claims.get("principal_type", PrincipalType.USER.value)
        try:
            principal_type = PrincipalType(principal_type_raw)
        except ValueError as exc:
            raise InvalidTokenError(
                f"bearer token names unknown principal_type '{principal_type_raw}'"
            ) from exc

        return Principal(
            principal_id=principal_id,
            principal_type=principal_type,
            roles=frozenset(claims.get("roles", [])),
        )


async def build_jwt_bearer_token_verifier(
    *, secret_provider: SecretProvider, signing_key_secret_reference: str
) -> JWTBearerTokenVerifier:
    """Resolves the signing key once at construction time, mirroring
    :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`."""
    secret = await secret_provider.resolve(signing_key_secret_reference)
    return JWTBearerTokenVerifier(signing_key=secret.reveal())
