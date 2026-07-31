"""Layer 7, secret value resolution (configuration_manager.md §4:
"Secret values — Resolved at point of use from ``secret://``
references"; ADR-0024 rule 1: "resolved at the moment of use... never
placed into a broadly-shared config object") — ``P01-S02-M01-T06``.

Wires the already-proven ``secrets_manager`` (``P01-S02-M19-T02``) into
the configuration merge: configuration_manager.md's own named remaining
gap was "a ``secret://`` reference appearing in ``platform.yaml`` today
is resolved by no one; it is carried through as a literal string."
:func:`resolve_secret_references` closes exactly that — recursing
through an already-merged layer 1-6 dict (the *winning* value per key,
decided by every lower layer first) and resolving each ``secret://``
reference through the injected ``SecretProvider``, at the correct
position: after precedence is resolved, not before.

**Resolved values are ``SecretValue``-wrapped, never raw strings**
(ADR-0024 rule 2) — this is why the result here is a plain ``dict``,
not a validated ``PlatformConfig``: no field on that model is
secret-shaped yet (Coding Standards: no speculative fields), and a
wrapped ``SecretValue`` could not satisfy a plain ``str`` field's type
even if one existed prematurely.
:meth:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager.
load_with_secrets_resolved` is the call site this Task wires in; the
first real secret-shaped field validates through ``PlatformConfig``
normally once a real consumer needs one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_os_kernel.secrets_manager.provider import SecretProvider

_SECRET_URI_PREFIX = "secret://"  # noqa: S105 -- a URI scheme prefix, not a credential


async def resolve_secret_references(
    values: Mapping[str, Any], provider: SecretProvider
) -> dict[str, Any]:
    """Recurses through ``values`` — nested mappings merge the same way
    :func:`~ai_os_kernel.configuration_manager.loader._deep_merge` does
    — and resolves every ``secret://`` string through ``provider``.
    Every other value, including one that merely contains the
    substring elsewhere, passes through unchanged: only a value whose
    *entire* string is a ``secret://`` reference is resolved."""
    resolved: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            resolved[key] = await resolve_secret_references(value, provider)
        elif isinstance(value, str) and value.startswith(_SECRET_URI_PREFIX):
            resolved[key] = await provider.resolve(value)
        else:
            resolved[key] = value
    return resolved
