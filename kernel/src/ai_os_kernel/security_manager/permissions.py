"""The role -> permission grants this step actually enforces.

authentication_authorization.md §4.2 documents five roles (``viewer``,
``operator``, ``approver``, ``maintainer``, ``admin``) against a full,
closed permission vocabulary published in the SDK
(``platform_sdk/schemas/manifest.schema.json``). Modelling that entire
vocabulary here would be speculative — no route exists yet for most of
those permissions to guard. This step models five permissions —
:data:`WORKFLOW_READ`/:data:`WORKFLOW_START` (from an earlier step),
:data:`PACK_READ`/:data:`PACK_MANAGE` (api_architecture.md §5:
"``pack:read`` / ``pack:manage`` | Read / install, activate, deactivate
packs"), and now :data:`SECRET_ACCESS` (``P01-S02-M19-T04``) — and the
role grants the docs give for them; a later step adds more permissions
and role grants as more routes are built, without changing this
module's shape.

**No ``approval:decide`` flat permission (considered and rejected,
``P03-S03-M30-T06``).** A route needing "may this principal decide
*some* approval" cannot be expressed correctly here: this module's own
flat, exact-string role lookup has no way to recognize a class-scoped
role like ``approver:release`` as also implying the bare ``approver``
grant — a principal legitimately holding *only*
``approver:approve-git-push`` (the realistic, minimal grant ADR-0023's
own role table describes — "Approval classes are grantable separately")
would be refused by a flat gate before ever reaching the real,
correctly class-scoped check. :mod:`ai_os_kernel.routes.approvals`
authenticates only (real Bearer/JWT verification, unchanged) and defers
the entire authorization decision to
:class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`,
which already does this correctly via
:func:`~ai_os_kernel.security_manager.approval_authorization.
is_authorized_to_decide_approval` — see that module's own docstring for
why it is a standalone function precisely because of this gap.

**Why only ``maintainer``/``admin`` get ``pack:read``/``pack:manage``.**
authentication_authorization.md §4.2's role table gives `viewer`
("Read workflows, experiments, gate results, health"), `operator`
("`viewer` + start/cancel/retry workflows, run experiments"), and
`approver` ("`viewer` + decide Human Approval Points") — none mentions
packs at all. `maintainer` is the first role the table names in
connection with packs at all: "`operator` + install/activate/deactivate
packs, edit non-security configuration." Granting `pack:read` to
`maintainer` too (not documented separately, but implied — managing a
pack requires being able to read it) is the "closest documented
permission" reasoning this step's own approved framing anticipated,
not an invented grant; `viewer`/`operator`/`approver` get neither,
since nothing in their documented grants mentions packs.

**Why only ``admin`` gets ``secret:access``.** §4.2's role table names
*only* `admin` in connection with secrets at all: "All, including
security policy, role assignment, and secret management. Every action
audited." `viewer`/`operator`/`approver`/`maintainer`'s documented
grants say nothing about secrets — the same "nothing documented, no
grant" discipline already applied to packs, not a narrower reading
invented for this step. The exact string `secret:access` is not itself
spelled out in the docs (only the prose "secret management" and the
design-goal example "secret access" at §2/§3) — chosen over the
literal example `secret:manage` (authentication_authorization.md line
92) because *resolving* a secret to use it is a routine read, not
administering the secrets subsystem; a future `secret:manage`
permission for backend/rotation administration would be a distinct,
narrower-still concept layered on top of this one, not this one
renamed.

This is deliberately **not** the full ADR-0023 monotonic-narrowing
chain (principal ∩ workflow ∩ agent ∩ tool declared permissions) — only
the principal's own role-derived permissions. Workflow/agent/tool
declared-permission intersection needs manifest-declared permissions,
which is Capability Manager territory not yet built.
"""

from __future__ import annotations

from collections.abc import Iterable

WORKFLOW_READ = "workflow:read"
WORKFLOW_START = "workflow:start"
PACK_READ = "pack:read"
PACK_MANAGE = "pack:manage"
SECRET_ACCESS = "secret:access"  # noqa: S105 -- a permission string, not a credential

# authentication_authorization.md §4.2's role table, reduced to the
# five permissions modelled above. Unknown roles grant nothing (deny by
# default) — see permissions_for_roles.
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({WORKFLOW_READ}),
    "operator": frozenset({WORKFLOW_READ, WORKFLOW_START}),
    "approver": frozenset({WORKFLOW_READ}),
    "maintainer": frozenset({WORKFLOW_READ, WORKFLOW_START, PACK_READ, PACK_MANAGE}),
    "admin": frozenset({WORKFLOW_READ, WORKFLOW_START, PACK_READ, PACK_MANAGE, SECRET_ACCESS}),
}


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    """Union the permissions granted by each of ``roles``.

    An unrecognised role name contributes no permissions rather than
    raising — a typo'd or not-yet-modelled role should deny the request,
    not crash it.
    """
    granted: set[str] = set()
    for role in roles:
        granted |= _ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)
