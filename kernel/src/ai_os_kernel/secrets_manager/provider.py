"""The persistence-boundary-style seam for Secrets Management: a
:class:`SecretProvider` resolves one secret reference to a
:class:`~ai_os_kernel.secrets_manager.value.SecretValue`.

Mirrors the same "one ``Protocol``, swappable implementations behind
it" pattern already used for
:class:`~ai_os_kernel.workflow_engine.lease.WorkflowLeaseRepository`
and every other backend seam in this codebase (ADR-0004:
interface-driven, configuration over code). ``async`` even though
:class:`~ai_os_kernel.secrets_manager.env_provider.EnvSecretProvider`
does no real I/O — every other backend ADR-0024 names (Vault, cloud
secret managers) does, and callers should not need to change when a
Vault-backed provider is substituted in later.
"""

from __future__ import annotations

from typing import Protocol

from ai_os_kernel.secrets_manager.value import SecretValue


class SecretProvider(Protocol):
    """Resolves a ``secret://...`` reference (ADR-0024) to a value.

    Implementations decide for themselves which ``provider`` segment of
    the reference they answer for and raise
    :class:`~ai_os_kernel.secrets_manager.errors.SecretResolutionError`
    for anything else, exactly as
    :meth:`~ai_os_kernel.workflow_engine.lease.WorkflowLeaseRepository.acquire`
    raises a structured error rather than returning a sentinel.
    """

    async def resolve(self, reference: str) -> SecretValue: ...
