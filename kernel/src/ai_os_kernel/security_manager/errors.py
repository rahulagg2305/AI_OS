"""Errors raised by the Security Manager's authentication/authorization
boundary (docs/03_architecture/kernel/security_manager.md,
docs/09_security/authentication_authorization.md)."""


class SecurityError(Exception):
    """Base class for every Security Manager error."""


class InvalidTokenError(SecurityError):
    """A bearer token failed verification: bad signature, expired,
    malformed, or missing a required claim.

    Never carries the token itself in its message — only the reason —
    mirroring :class:`~ai_os_kernel.secrets_manager.errors.SecretResolutionError`'s
    own "name the reference, never the value" discipline.
    """


class ApprovalNotAuthorizedError(SecurityError):
    """A principal attempted to decide a Human Approval Point it is not
    authorized for — holds neither the ``admin`` role nor the
    approval's own class-scoped ``approver:<approval_class>`` role
    (ADR-0023's Roles table: "Approval classes are grantable separately
    — for example ``approver:release`` distinct from
    ``approver:architecture``"). Raised **before** any write is
    attempted (:mod:`ai_os_kernel.security_manager.approval_authorization`'s
    own check runs first) — the approval itself is left completely
    untouched, not a rolled-back one.
    """
