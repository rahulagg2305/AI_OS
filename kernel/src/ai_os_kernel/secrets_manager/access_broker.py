"""The Access Broker (docs/09_security/secrets_management.md §5:
"Access Broker — authorization + audit per access") — ``P01-S02-M19-T04``,
closing the module's own long-named gap. `env_provider.py`'s own
docstring: "No rotation, no audit trail beyond what the caller does
with the result" — this is that missing gate and trail.

**Authorization reuses ``security_manager``'s existing
``SecurityContext``** (``P03-S05-M14-T01``'s ``Principal``, ADR-0023)
rather than inventing a second permission model.
authentication_authorization.md §4.2's role table names only ``admin``
in connection with secrets at all ("All, including security policy,
role assignment, and secret management. Every action audited") — so
:data:`~ai_os_kernel.security_manager.permissions.SECRET_ACCESS` is
granted to ``admin`` only (see that module's own docstring for the
full reasoning).

**Audit reuses the already-proven, hash-chained
``governance.audit_log`` writer** (``P01-S05-M04-T05``/``T06``), not
``governance.config_changes`` — that table's shape (digests of an
old/new *config value*) does not fit an authorization decision at all,
whereas ``AuditOutcome.ALLOWED``/``DENIED``/``FAILURE`` already model
exactly this. ``resource_id`` is the secret *reference* string itself
(e.g. ``"secret://env/llm-api-key"``) — never the resolved value,
matching secrets_management.md §8: "Never record the secret value
itself." Every access is audited, allowed or denied alike — a denied
attempt is itself a real, security-relevant event, not a silent no-op.
"""

from __future__ import annotations

from ai_os_kernel.observability.audit import AuditLogWriter, AuditOutcome
from ai_os_kernel.secrets_manager.errors import AccessDeniedError, SecretResolutionError
from ai_os_kernel.secrets_manager.provider import SecretProvider
from ai_os_kernel.secrets_manager.value import SecretValue
from ai_os_kernel.security_manager.models import SecurityContext
from ai_os_kernel.security_manager.permissions import SECRET_ACCESS


class AccessBroker:
    """Gates and audits every secret resolution — this Task's own
    Input (principal plus reference) and Output (allow or deny,
    audited)."""

    def __init__(self, *, provider: SecretProvider, audit_log: AuditLogWriter) -> None:
        self._provider = provider
        self._audit_log = audit_log

    async def resolve(self, reference: str, *, context: SecurityContext) -> SecretValue:
        """Resolves ``reference`` on ``context``'s behalf, or raises
        :class:`~ai_os_kernel.secrets_manager.errors.AccessDeniedError`
        — auditing the outcome either way, before returning or
        raising."""
        if not context.has_permission(SECRET_ACCESS):
            await self._audit_log.record(
                event_type="secret.access.denied",
                principal_id=context.principal.principal_id,
                principal_type=context.principal.principal_type,
                outcome=AuditOutcome.DENIED,
                detail={"permission": SECRET_ACCESS},
                resource_type="secret",
                resource_id=reference,
            )
            raise AccessDeniedError(
                f"principal {context.principal.principal_id!r} lacks "
                f"'{SECRET_ACCESS}' — cannot resolve {reference!r}"
            )

        try:
            value = await self._provider.resolve(reference)
        except SecretResolutionError:
            await self._audit_log.record(
                event_type="secret.access.failed",
                principal_id=context.principal.principal_id,
                principal_type=context.principal.principal_type,
                outcome=AuditOutcome.FAILURE,
                detail={},
                resource_type="secret",
                resource_id=reference,
            )
            raise

        await self._audit_log.record(
            event_type="secret.access.allowed",
            principal_id=context.principal.principal_id,
            principal_type=context.principal.principal_type,
            outcome=AuditOutcome.ALLOWED,
            detail={},
            resource_type="secret",
            resource_id=reference,
        )
        return value
