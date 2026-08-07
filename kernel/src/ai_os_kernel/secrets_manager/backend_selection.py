"""The real ``AIOS_SECRET_BACKEND`` switch secrets_management.md §5
documents ("Backend is selected by ``AIOS_SECRET_BACKEND``") but that
this codebase never actually implemented — every real caller
(``kernel/src/ai_os_kernel/bootstrap.py``) constructed
:class:`~ai_os_kernel.secrets_manager.env_provider.EnvSecretProvider`
directly, unconditionally, three separate times (``P07-S02-M19-T01``,
"Vault secrets backend," closes this alongside adding the Vault
backend itself — building Vault without also building its own
documented selection switch would leave it permanently unreachable by
any real composition root).

Mirrors :func:`~ai_os_kernel.bootstrap._build_token_verifier`'s own
"select the real backend only when it is fully configured, default
unchanged otherwise" shape (``P07-S02-M14-T01``, OIDC) — except this
function *raises* :class:`~ai_os_kernel.secrets_manager.errors.
SecretBackendConfigError` on a genuinely incomplete ``vault``
configuration rather than degrading to ``env``: a secret meant to come
from Vault silently resolving from an environment variable instead
(finding an unrelated value, or nothing) is a worse, quieter failure
than refusing to start.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretBackendConfigError
from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.secrets_manager.vault_provider import build_vault_secret_provider

# secrets_management.md §5's own documented default ("env" — local
# development only, ADR-0024) — every environment that never sets this
# variable at all keeps today's exact, unchanged behaviour.
_DEFAULT_BACKEND = "env"
_VAULT_BACKEND = "vault"

# Vault's own upstream convention default mount path for its KV v2
# secrets engine (`vault secrets enable kv-v2` with no `-path=` mounts
# here) — a real, disclosed default, overridable, not a hidden
# hardcode: see VaultSecretProvider's own docstring.
_DEFAULT_VAULT_KV_MOUNT = "secret"


def _resolve_backend_name(env: Mapping[str, str] | None) -> str:
    """The one real place ``AIOS_SECRET_BACKEND`` is read — shared by
    :func:`build_secret_provider_from_env` (which backend object to
    construct) and :func:`secret_reference_for` (which backend a
    reference should name), so the two can never disagree about which
    backend is actually selected."""
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    return resolved_env.get("AIOS_SECRET_BACKEND", _DEFAULT_BACKEND)


def build_secret_provider_from_env(env: Mapping[str, str] | None = None) -> SecretProvider:
    """Reads ``AIOS_SECRET_BACKEND`` (default ``"env"``) from ``env``
    (defaults to the real process environment) and returns the real
    provider it names.

    ``env`` is injectable so a test never has to mutate real process
    state to exercise every branch (ADR-0004; mirrors every other
    injected-dependency seam in this codebase).
    """
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    backend = _resolve_backend_name(env)

    if backend == _DEFAULT_BACKEND:
        return EnvSecretProvider(env=env)

    if backend == _VAULT_BACKEND:
        address = resolved_env.get("AIOS_VAULT_ADDR")
        token = resolved_env.get("AIOS_VAULT_TOKEN")
        if not address or not token:
            raise SecretBackendConfigError(
                "AIOS_SECRET_BACKEND='vault' requires both AIOS_VAULT_ADDR and "
                "AIOS_VAULT_TOKEN to be set"
            )
        mount = resolved_env.get("AIOS_VAULT_KV_MOUNT", _DEFAULT_VAULT_KV_MOUNT)
        return build_vault_secret_provider(address=address, token=token, mount=mount)

    raise SecretBackendConfigError(
        f"AIOS_SECRET_BACKEND='{backend}' is not a real backend — expected "
        f"'{_DEFAULT_BACKEND}' or '{_VAULT_BACKEND}' (secrets_management.md §5)"
    )


def secret_reference_for(name: str, env: Mapping[str, str] | None = None) -> str:
    """Builds ``secret://<current-backend>/<name>`` for whichever
    backend :func:`build_secret_provider_from_env` would itself select
    from the identical ``env`` — so a composition root's own hardcoded
    reference constants (the Anthropic API key, the JWT signing key)
    genuinely move to Vault the moment ``AIOS_SECRET_BACKEND=vault`` is
    set, rather than staying pinned to ``env://`` while only the
    provider object switches underneath them (which would refuse every
    such reference outright — a real, structural gap found and closed
    in the same step that added the Vault backend, not left half-wired).

    ``name`` is the reference's own path-like identifier (e.g.
    ``"llm/anthropic-api-key"``) — identical across every backend;
    only the ``<provider>`` segment changes.
    """
    return f"secret://{_resolve_backend_name(env)}/{name}"
