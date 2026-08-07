"""The HashiCorp Vault secret backend (``P07-S02-M19-T01``) — ADR-0024's
own "reference production backend," the third real
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`
implementation after :class:`~ai_os_kernel.secrets_manager.env_provider.
EnvSecretProvider` and :class:`~ai_os_kernel.secrets_manager.file_provider.
FileSecretProvider`.

**KV v2 only, token authentication only — both real, disclosed
narrower scopes, not silent gaps.** Vault's KV secrets engine has two
incompatible versions; this resolves ``secret://vault/<name>[#<version>]``
against a KV **v2** mount (Vault's own default when you enable ``secret/``
today, and the version that genuinely supports the reference format's
own ``#<version>`` segment — KV v1 has no version history at all).
Authentication is a pre-issued Vault token, read directly from
``AIOS_VAULT_TOKEN`` (see :mod:`~ai_os_kernel.secrets_manager.backend_selection`)
— never resolved through this module itself, since the credential that
unlocks Vault cannot itself be stored *in* Vault. AppRole/Kubernetes
auth (real alternatives a production Vault deployment may prefer) are
unbuilt; nothing here assumes they will look like this.

**No hardcoded secret-field name.** A Vault KV v2 secret's ``data.data``
is a JSON object that can hold any number of named fields — this
module does not assume one is called ``value`` or any other specific
name (the exact "no hardcoded values" this codebase's standing rules
forbid). A reference resolves only when the object holds **exactly
one** field; two or more, or zero, is refused as genuinely ambiguous
rather than guessing which field the caller meant.
"""

from __future__ import annotations

import httpx

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.reference import parse_secret_reference
from ai_os_kernel.secrets_manager.value import SecretValue

_PROVIDER_NAME = "vault"
_VAULT_TOKEN_HEADER = "X-Vault-Token"  # noqa: S105 -- a header name, not a credential


class VaultSecretProvider:
    """Resolves ``secret://vault/<name>[#<version>]`` against a real
    Vault KV v2 mount, over an already-constructed ``httpx.AsyncClient``
    (its ``base_url`` already pointed at the Vault server and its
    default headers already carrying the real token — see
    :func:`build_vault_secret_provider`) — the identical injected-client
    shape :class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`
    already establishes for another HTTP-backed adapter in this
    codebase.

    ``mount`` is the KV v2 secrets-engine mount path (Vault's own
    convention default is ``"secret"``, e.g. ``vault secrets enable
    -path=secret kv-v2``) — a real, overridable default, not a hidden
    hardcode: see :func:`build_vault_secret_provider`'s own
    ``AIOS_VAULT_KV_MOUNT``.
    """

    def __init__(self, *, client: httpx.AsyncClient, mount: str) -> None:
        self._client = client
        self._mount = mount

    async def resolve(self, reference: str) -> SecretValue:
        parsed = parse_secret_reference(reference)

        if parsed.provider != _PROVIDER_NAME:
            raise SecretResolutionError(
                f"'{reference}' names provider '{parsed.provider}', not "
                f"'{_PROVIDER_NAME}' — VaultSecretProvider only resolves "
                f"'{_PROVIDER_NAME}://' references"
            )

        params: dict[str, str] = {}
        if parsed.version is not None:
            if not parsed.version.isdigit():
                raise SecretResolutionError(
                    f"'{reference}' requests version '{parsed.version}', but Vault KV v2 "
                    "versions are non-negative integers"
                )
            params["version"] = parsed.version

        path = f"v1/{self._mount}/data/{parsed.name}"
        try:
            response = await self._client.get(path, params=params)
        except httpx.TransportError as exc:
            raise SecretResolutionError(
                f"'{reference}' could not be resolved — Vault is unreachable: {exc}"
            ) from exc

        if response.status_code == 404:
            raise SecretResolutionError(
                f"'{reference}' resolves to Vault path '{self._mount}/{parsed.name}', "
                "which does not exist"
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SecretResolutionError(
                f"'{reference}' could not be resolved — Vault returned "
                f"{response.status_code}: {exc}"
            ) from exc

        body = response.json()
        data = body.get("data", {}).get("data", {})
        if not isinstance(data, dict) or len(data) != 1:
            raise SecretResolutionError(
                f"'{reference}' resolves to a Vault secret holding "
                f"{len(data) if isinstance(data, dict) else 'a non-object'} field(s) "
                f"({sorted(data) if isinstance(data, dict) else data!r}) — VaultSecretProvider "
                "only resolves a secret with exactly one field, since no field name is assumed"
            )
        (value,) = data.values()
        if not isinstance(value, str):
            raise SecretResolutionError(
                f"'{reference}' resolves to a Vault secret whose one field is not a string"
            )
        return SecretValue(value)


def build_vault_secret_provider(
    *, address: str, token: str, mount: str = "secret"
) -> VaultSecretProvider:
    """Constructs the ``httpx.AsyncClient`` pointed at ``address`` (the
    Vault server's own root, e.g. ``http://127.0.0.1:8200``) with the
    real token attached as a default header, and the real
    :class:`VaultSecretProvider`.

    Deliberately synchronous, mirroring
    :func:`~ai_os_kernel.llm_gateway.adapters.local_adapter.build_local_adapter`:
    no secret to resolve and no I/O of its own — ``address``/``token``
    are plain configuration values the composition root already holds
    (see :mod:`~ai_os_kernel.secrets_manager.backend_selection` for
    where ``token`` genuinely comes from: a raw environment variable,
    never a ``secret://`` reference).
    """
    client = httpx.AsyncClient(base_url=address, headers={_VAULT_TOKEN_HEADER: token})
    return VaultSecretProvider(client=client, mount=mount)
