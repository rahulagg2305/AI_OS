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
- :class:`AccessBroker` (added 2026-07-31, ``P01-S02-M19-T04``) — gates
  every resolution on ``security_manager``'s own
  ``secret:access`` permission (``admin`` role only) and audits every
  attempt, allowed or denied, as a real, hash-chained
  ``governance.audit_log`` row (reusing
  :mod:`ai_os_kernel.observability.audit`, not reimplementing it). See
  :mod:`ai_os_kernel.secrets_manager.access_broker`.
- :class:`CachingSecretProvider` (added 2026-08-01, ``P01-S02-M19-T05``) —
  wraps any :class:`SecretProvider` with a per-reference,
  bounded-lifetime (TTL) cache, plus an explicit
  :meth:`~ai_os_kernel.secrets_manager.cache.CachingSecretProvider.invalidate`
  hook for a caller that learns a secret was rotated at its source
  before the TTL naturally expires. See
  :mod:`ai_os_kernel.secrets_manager.cache`.
- :func:`~ai_os_kernel.secrets_manager.leak_scan.scan_rendered_prompt_for_secret_leak`
  (added 2026-08-01, ``P01-S02-M19-T06``) — defence-in-depth: refuses
  to let a rendered prompt reach a model if any secret value resolved
  for it appears verbatim in the content, and audits the block. See
  :mod:`ai_os_kernel.secrets_manager.leak_scan`.
- **Wired into the Configuration Manager** (``P01-S02-M01-T06``):
  :func:`ai_os_kernel.configuration_manager.resolve_secret_references`
  resolves every ``secret://`` reference surviving that module's own
  layer 1-6 merge through a ``SecretProvider`` — not yet routed through
  :class:`AccessBroker` or :class:`CachingSecretProvider`, since that
  resolution path has no
  :class:`~ai_os_kernel.security_manager.models.SecurityContext` to
  gate with today, and every layer-1-6 merge already re-reads current
  values on every call.

Not yet implemented: age/SOPS encrypted-file decryption, HashiCorp
Vault, cloud secret managers, and wiring
:class:`AccessBroker`/:class:`CachingSecretProvider`/the leak scan into
any specific consumer (LLM Gateway, Git Integration Service, ...).
None of those exist yet, so none of them use this module yet.
"""

from ai_os_kernel.secrets_manager.access_broker import AccessBroker
from ai_os_kernel.secrets_manager.cache import CachingSecretProvider
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.secrets_manager.errors import (
    AccessDeniedError,
    SecretLeakDetectedError,
    SecretResolutionError,
)
from ai_os_kernel.secrets_manager.file_provider import FileSecretProvider
from ai_os_kernel.secrets_manager.leak_scan import scan_rendered_prompt_for_secret_leak
from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.secrets_manager.reference import SecretReference, parse_secret_reference
from ai_os_kernel.secrets_manager.value import SecretValue

__all__ = [
    "AccessBroker",
    "AccessDeniedError",
    "CachingSecretProvider",
    "EnvSecretProvider",
    "FileSecretProvider",
    "SecretLeakDetectedError",
    "SecretProvider",
    "SecretReference",
    "SecretResolutionError",
    "SecretValue",
    "parse_secret_reference",
    "scan_rendered_prompt_for_secret_leak",
]
