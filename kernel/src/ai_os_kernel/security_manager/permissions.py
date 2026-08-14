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
# api_architecture.md §5's own documented row ("workflow:control |
# Cancel, retry, resume"), added (P06-S01-M36-T04) the moment a real
# route (POST /api/v1/workflows/{id}/cancel) first needs to enforce it.
# Granted identically to WORKFLOW_START — §4.2's own table names both
# together in the same clause ("operator: ... start / cancel / retry
# workflows"), so no role holds one without the other.
WORKFLOW_CONTROL = "workflow:control"
PACK_READ = "pack:read"
PACK_MANAGE = "pack:manage"
SECRET_ACCESS = "secret:access"  # noqa: S105 -- a permission string, not a credential
CONFIG_READ = "config:read"
CONFIG_MANAGE = "config:manage"
# authentication_authorization.md §4.2's own `viewer` grant explicitly
# names "experiments, gate results" alongside "workflows" — this
# permission is that real, already-documented grant, added
# (P06-S03-M39-T03) the moment a real route first needs to enforce it.
EVALUATION_READ = "evaluation:read"
# api_architecture.md §5's own documented row ("approval:read | See
# pending approvals"), added (P06-S03-M39-T02) the moment a real route
# (GET /api/v1/approvals) first needs to enforce it. Unlike
# `approval:decide:<class>` (never modelled here at all — see this
# module's own docstring on why a class-scoped permission family cannot
# be expressed by this flat dict), `approval:read` is not documented as
# class-scoped anywhere — it is a flat "may see the pending queue at
# all" gate, granted only where §4.2's own role table actually mentions
# approvals: `approver` ("`viewer` + decide Human Approval Points" —
# deciding requires first seeing) and `admin` ("All"). `viewer`/
# `operator`/`maintainer`'s own documented grants say nothing about
# approvals, the identical "nothing documented, no grant" discipline
# already applied to packs/secrets/configuration above.
APPROVAL_READ = "approval:read"
# api_architecture.md §5's own documented row ("experiment:read /
# experiment:run | Read / launch experiments"), added (P04-S01-M12-T12)
# the moment a real route (POST /api/v1/experiments) first needs to
# enforce a write. Only the write half is a new constant here: the read
# half (`experiment:read`) is already covered by EVALUATION_READ, whose
# own comment above names "experiments" — this codebase never split the
# two, and both `GET /experiments` and `GET /gates/results` read under
# `evaluation:read`. §5 names no separate "define" permission, so both
# defining and (the future) launching an experiment fall under this one
# write capability, granted to exactly the `operator`/`maintainer`/
# `admin` roles §4.2's own table documents as able to "run experiments"
# (viewer/approver read only) — reusing §5's documented vocabulary
# rather than inventing a third string.
EXPERIMENT_RUN = "experiment:run"
# `knowledge:read` is **not invented here** — it is already in the
# closed permission vocabulary ADR-0023 requires be "published in the
# SDK": `platform_sdk/schemas/manifest.schema.json` has listed
# `knowledge:read`/`knowledge:write` since the schema was written, so a
# pack could already declare it while nothing Kernel-side could enforce
# it. Added (`P02-S04-M09-T08`) the moment a real caller — the Access /
# Filter Layer in `knowledge_manager.query_engine` — first needs to
# enforce it, the identical "no constant until a real enforcement point
# exists" discipline every permission above already follows.
#
# Only the read half is modelled: nothing in this codebase writes
# knowledge on behalf of a principal (ingestion is a platform startup
# scan with no principal at all), so a `knowledge:write` constant would
# be a permission with no enforcement point — exactly what the rule
# above exists to prevent.
KNOWLEDGE_READ = "knowledge:read"

# authentication_authorization.md §4.2's role table, reduced to the
# permissions modelled above. Unknown roles grant nothing (deny by
# default) — see permissions_for_roles.
#
# CONFIG_READ/CONFIG_MANAGE (P06-S01-M36-T04) follow the identical
# "nothing documented for viewer/operator/approver, no grant" discipline
# PACK_READ/PACK_MANAGE already established: §4.2 mentions configuration
# only for `maintainer` ("edit non-security configuration") and
# implicitly `admin` ("All") — neither viewer, operator, nor approver's
# own documented grants say anything about configuration, the identical
# reasoning already applied to packs.
#
# KNOWLEDGE_READ (`P02-S04-M09-T08`) is granted to **every** role, which
# is a deliberate departure from the "nothing documented, no grant"
# discipline above and is documented rather than silent: §4.2's role
# table says nothing about knowledge at all, so that discipline offers
# no answer here. Knowledge is the platform's own approved
# documentation — `knowledge_manager.md` §3 puts its authority at
# "Highest" and §6 calls repository documentation "the primary source of
# truth" — and no document anywhere suggests reading it is privileged or
# ranks it against workflow/evaluation reads. Product-owner decision,
# 2026-08-14. The gate therefore bites on unauthenticated and
# unpermissioned callers, not on ordinary roles.
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({WORKFLOW_READ, EVALUATION_READ, KNOWLEDGE_READ}),
    "operator": frozenset(
        {
            WORKFLOW_READ,
            WORKFLOW_START,
            WORKFLOW_CONTROL,
            EVALUATION_READ,
            EXPERIMENT_RUN,
            KNOWLEDGE_READ,
        }
    ),
    "approver": frozenset({WORKFLOW_READ, EVALUATION_READ, APPROVAL_READ, KNOWLEDGE_READ}),
    "maintainer": frozenset(
        {
            WORKFLOW_READ,
            WORKFLOW_START,
            WORKFLOW_CONTROL,
            PACK_READ,
            PACK_MANAGE,
            CONFIG_READ,
            CONFIG_MANAGE,
            EVALUATION_READ,
            EXPERIMENT_RUN,
            KNOWLEDGE_READ,
        }
    ),
    "admin": frozenset(
        {
            WORKFLOW_READ,
            WORKFLOW_START,
            WORKFLOW_CONTROL,
            PACK_READ,
            PACK_MANAGE,
            SECRET_ACCESS,
            CONFIG_READ,
            CONFIG_MANAGE,
            EVALUATION_READ,
            APPROVAL_READ,
            EXPERIMENT_RUN,
            KNOWLEDGE_READ,
        }
    ),
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
