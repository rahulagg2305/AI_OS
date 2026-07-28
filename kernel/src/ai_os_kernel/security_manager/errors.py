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
