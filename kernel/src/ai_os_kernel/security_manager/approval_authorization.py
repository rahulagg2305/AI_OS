"""Real enforcement of ADR-0023's per-class Human Approval Point grant
(Roles table: "``approver`` — ``viewer`` + decide Human Approval
Points. Approval classes are grantable separately (for example
``approver:release`` distinct from ``approver:architecture``)") — the
one piece of the Roles table
(:doc:`/09_security/authentication_authorization`) §4.2 the flat
:func:`~ai_os_kernel.security_manager.permissions.permissions_for_roles`
mechanism cannot express: it looks up a fixed set of five exact role
strings against a static grant table, with no way to represent a role
*family* parameterized by an arbitrary, workflow-declared class.

Deliberately a standalone function, not a :mod:`~ai_os_kernel.
security_manager.permissions` addition. ``SecurityContext.permissions``
is a *request-scoped, role-derived* frozenset answering "what can this
principal do at all" — computed once, independent of any particular
resource. This answers a narrower, per-resource question — "may this
principal decide *this* approval" — that depends on data
(``approval.approval_class``) the flat computation never sees and has
no field for. ``admin`` still shortcuts every check (§4.2: "All,
including security policy, role assignment, and secret management").

A bare ``approver`` role (no class suffix) grants nothing here — every
example ADR-0023 itself gives is class-scoped (``approver:release``,
``approver:architecture``); an unscoped grant is not a documented
concept to fall back to.
"""

from __future__ import annotations

from ai_os_kernel.security_manager.models import Principal

ADMIN_ROLE = "admin"
_APPROVER_ROLE_PREFIX = "approver:"


def is_authorized_to_decide_approval(principal: Principal, approval_class: str) -> bool:
    """True iff ``principal`` may record a decision for an approval of
    ``approval_class`` — holds ``admin``, or the exact class-scoped
    role ``approver:<approval_class>``."""
    if ADMIN_ROLE in principal.roles:
        return True
    return f"{_APPROVER_ROLE_PREFIX}{approval_class}" in principal.roles
