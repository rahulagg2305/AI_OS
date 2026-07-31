"""Secrets Management — secrets are referenced by URI and resolved at
point of use, never stored in configuration, packs, or the database as
literal values (ADR-0024, docs/09_security/secrets_management.md).

Implemented so far (Stage A):

- :func:`~ai_os_kernel.secrets_manager.reference.parse_secret_reference`
  parses the ADR-0024 reference format,
  ``secret://<provider>/<name>[#<version>]``, into a
  :class:`~ai_os_kernel.secrets_manager.reference.SecretReference` —
  backend-agnostic, shared by every provider.
- :class:`SecretValue` wraps a resolved value so it can never be
  accidentally logged or serialised: ``__str__``/``__repr__`` return
  ``***``; the raw value requires an explicit
  :meth:`~ai_os_kernel.secrets_manager.value.SecretValue.reveal` call.
- :class:`SecretProvider` is the ``Protocol`` every backend implements.
- :class:`EnvSecretProvider` — the ``env`` backend, explicitly scoped by
  ADR-0024 to local development only.
- :class:`FileSecretProvider` (added 2026-07-31, ``P01-S02-M19-T03``) —
  the mounted-file backend: one file per secret under an injected root,
  the shape Docker secrets and Kubernetes ``secret`` volumes already
  present. **Plaintext mounted file, not age/SOPS decryption** — see
  that module's own docstring for why the distinction is stated rather
  than implied.

Not yet implemented: age/SOPS encrypted-file decryption, HashiCorp
Vault, cloud secret managers, the Access Broker (authorization + audit
per access), TTL caching with rotation invalidation, the prompt-assembly
scan that rejects a resolved secret value reaching a model, and wiring
into any consumer (LLM Gateway, Git Integration Service, Configuration
Manager, ...). None of those exist yet, so none of them use this module
yet.
"""

from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.file_provider import FileSecretProvider
from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.secrets_manager.reference import SecretReference, parse_secret_reference
from ai_os_kernel.secrets_manager.value import SecretValue

__all__ = [
    "EnvSecretProvider",
    "FileSecretProvider",
    "SecretProvider",
    "SecretReference",
    "SecretResolutionError",
    "SecretValue",
    "parse_secret_reference",
]
