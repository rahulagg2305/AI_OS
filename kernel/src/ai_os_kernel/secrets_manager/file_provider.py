"""The mounted-file secret backend — the second real
:class:`~ai_os_kernel.secrets_manager.provider.SecretProvider`, after
:class:`~ai_os_kernel.secrets_manager.env_provider.EnvSecretProvider`.

Resolves ``secret://file/<name>`` by reading one file per secret from a
configured root directory, the shape a container orchestrator already
presents a mounted secret in (Docker secrets at ``/run/secrets/<name>``,
Kubernetes ``secret`` volumes at ``/etc/secrets/<name>``). ADR-0024
scopes a file backend to "single-node deployments"; this is the
directly-useful form of that for a containerised single node, and it is
strictly better than the ``env`` backend on ADR-0024's own stated
objection to environment variables — a mounted file is **not** inherited
by child processes, so it does not leak into a sandbox, a crash dump, or
a process listing merely by existing.

**Scope, stated rather than implied: this is a plaintext mounted file,
not age/SOPS decryption.** ADR-0024's backend table names the row
"Encrypted local file (age/SOPS)". Confidentiality here comes from the
orchestrator (encrypted at rest in etcd or the Docker secret store) and
from filesystem permissions, not from this process decrypting anything —
no age/SOPS dependency is introduced. Decrypting an age/SOPS file is a
genuinely different capability and remains unbuilt.

**Traversal is refused, not sanitised.** A reference whose ``<name>``
would resolve outside ``root`` raises rather than being silently
rewritten, so a malformed or hostile reference can never read an
arbitrary host file. This matters more here than for ``env``: a filename
is attacker-shaped input in a way an environment-variable lookup is not.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.reference import parse_secret_reference
from ai_os_kernel.secrets_manager.value import SecretValue

_PROVIDER_NAME = "file"


class FileSecretProvider:
    """Reads one secret per file from ``root``.

    ``root`` is required and injected — there is no default path. A
    real deployment's mount point is deployment configuration
    (``/run/secrets`` and ``/etc/secrets`` are both real conventions and
    neither is universal), so guessing one here would be exactly the
    hardcoded value this codebase's standing rules forbid.

    A secret's value is the file's decoded contents with **one** trailing
    newline stripped: writing a file without a trailing newline is
    awkward for humans and for most tooling, so requiring it would make
    the common case error-prone. Interior whitespace and any further
    trailing newlines are preserved exactly, because a multi-line secret
    (a PEM private key) is a real case and must round-trip byte-for-byte.
    """

    def __init__(self, *, root: Path) -> None:
        self._root = root

    async def resolve(self, reference: str) -> SecretValue:
        parsed = parse_secret_reference(reference)

        if parsed.provider != _PROVIDER_NAME:
            raise SecretResolutionError(
                f"'{reference}' names provider '{parsed.provider}', not "
                f"'{_PROVIDER_NAME}' — FileSecretProvider only resolves "
                f"'{_PROVIDER_NAME}://' references"
            )
        if parsed.version is not None:
            raise SecretResolutionError(
                f"'{reference}' requests version '{parsed.version}', but the "
                f"'{_PROVIDER_NAME}' backend has no versioning — a mounted file "
                "is always exactly one current value"
            )

        root = self._root.resolve()
        candidate = (root / parsed.name).resolve()
        if candidate != root and root not in candidate.parents:
            raise SecretResolutionError(
                f"'{reference}' resolves outside the configured secrets root — refusing to read it"
            )

        try:
            raw = candidate.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SecretResolutionError(
                f"'{reference}' resolves to '{candidate}', which does not exist"
            ) from None
        except OSError as exc:
            # Unreadable for any other real reason (a directory, a
            # permission denial, a broken mount). The message never
            # includes file *contents* — only the path and the OS reason.
            raise SecretResolutionError(
                f"'{reference}' resolves to '{candidate}', which could not be read: {exc}"
            ) from exc

        return SecretValue(raw.removesuffix("\n"))
