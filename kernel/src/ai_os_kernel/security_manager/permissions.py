"""The role -> permission grants this step actually enforces.

authentication_authorization.md §4.2 documents five roles (``viewer``,
``operator``, ``approver``, ``maintainer``, ``admin``) against a full,
closed permission vocabulary published in the SDK
(``platform_sdk/schemas/manifest.schema.json``). Modelling that entire
vocabulary here would be speculative — no route exists yet for most of
those permissions to guard. This step models four permissions —
:data:`WORKFLOW_READ`/:data:`WORKFLOW_START` (from an earlier step) and
now :data:`PACK_READ`/:data:`PACK_MANAGE` (api_architecture.md §5:
"``pack:read`` / ``pack:manage`` | Read / install, activate, deactivate
packs") — and the role grants the docs give for them; a later step adds
more permissions and role grants as more routes are built, without
changing this module's shape.

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

# authentication_authorization.md §4.2's role table, reduced to the
# four permissions modelled above. Unknown roles grant nothing (deny by
# default) — see permissions_for_roles.
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({WORKFLOW_READ}),
    "operator": frozenset({WORKFLOW_READ, WORKFLOW_START}),
    "approver": frozenset({WORKFLOW_READ}),
    "maintainer": frozenset({WORKFLOW_READ, WORKFLOW_START, PACK_READ, PACK_MANAGE}),
    "admin": frozenset({WORKFLOW_READ, WORKFLOW_START, PACK_READ, PACK_MANAGE}),
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
