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


class RoleAdministrationNotAuthorizedError(SecurityError):
    """A principal attempted to grant or revoke a role without holding
    ``admin`` — the same "administered by ``admin`` only" reading
    authentication_authorization.md §4.2's role table already gives
    role/secret administration (`RoleAdministrationService`'s own
    module docstring has the full reasoning). Raised, and audited as a
    real ``DENIED`` event, **before** any write is attempted."""


class RoleGrantNotActiveError(SecurityError):
    """A revoke was attempted against a role that is not (or no longer)
    an active grant for that principal — already revoked, or genuinely
    never granted. Mirrors :class:`~ai_os_kernel.workflow_engine.errors.
    ApprovalNotPendingError`'s own "guards a state-transition write
    against acting twice" shape."""


class RoleGrantAlreadyActiveError(SecurityError):
    """A grant was attempted for a (principal, role) pair that already
    has a real, active grant — refused rather than silently accepted as
    a no-op, the identical "a second write against already-settled
    state is a clear error, not silently swallowed" discipline
    :class:`RoleGrantNotActiveError` applies in the opposite direction.
    Enforced by ``security.role_grants``'s own real, atomic partial
    unique index — never a separate, race-prone pre-check read."""
