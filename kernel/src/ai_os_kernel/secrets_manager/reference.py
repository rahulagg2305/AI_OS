"""Parses the secret reference URI format ADR-0024 defines:
``secret://<provider>/<name>[#<version>]``, for example
``secret://vault/llm/anthropic-api-key``.

This parsing is backend-agnostic and shared by every
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`
implementation (only :class:`~ai_os_kernel.secrets_manager.env_provider.EnvSecretProvider`
exists so far) — each provider parses a reference the same way and then
decides for itself whether ``provider`` names it and whether it can
honor a ``version``.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.secrets_manager.errors import SecretResolutionError

# provider: lower snake, e.g. "env", "vault". name: a path-like
# identifier (Vault-style nested paths are an explicit example in
# ADR-0024: "secret://vault/llm/anthropic-api-key"). version: an
# opaque token, meaning is entirely backend-defined.
_REFERENCE_PATTERN = re.compile(
    r"^secret://(?P<provider>[a-z][a-z0-9_]*)/(?P<name>[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)"
    r"(?:#(?P<version>[A-Za-z0-9_.\-]+))?$"
)


class SecretReference(BaseModel):
    """One parsed ``secret://...`` reference."""

    model_config = ConfigDict(frozen=True)

    provider: str
    name: str
    version: str | None


def parse_secret_reference(reference: str) -> SecretReference:
    """Raise :class:`SecretResolutionError` if ``reference`` does not
    match the ADR-0024 URI format; otherwise return its parsed parts."""
    match = _REFERENCE_PATTERN.match(reference)
    if match is None:
        raise SecretResolutionError(
            f"'{reference}' is not a valid secret reference — expected "
            "'secret://<provider>/<name>[#<version>]' (ADR-0024)"
        )
    return SecretReference(
        provider=match.group("provider"),
        name=match.group("name"),
        version=match.group("version"),
    )
