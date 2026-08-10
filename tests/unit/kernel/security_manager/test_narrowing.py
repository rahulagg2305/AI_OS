"""ADR-0023's monotonic narrowing rule — the actual security property
this chain exists to guarantee: authority only ever shrinks along the
principal -> workflow -> agent -> tool invocation chain, and nothing
downstream of the principal can ever widen it. ``P03-S05-M14-T03``.
"""

from __future__ import annotations

from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.narrowing import is_permitted, narrow_permissions
from ai_os_kernel.security_manager.permissions import (
    APPROVAL_READ,
    CONFIG_MANAGE,
    CONFIG_READ,
    EVALUATION_READ,
    PACK_MANAGE,
    PACK_READ,
    SECRET_ACCESS,
    WORKFLOW_CONTROL,
    WORKFLOW_READ,
    WORKFLOW_START,
    permissions_for_roles,
)


def _admin_context() -> SecurityContext:
    return SecurityContext(
        principal=Principal(
            principal_id="admin-1", principal_type=PrincipalType.USER, roles=frozenset({"admin"})
        ),
        permissions=permissions_for_roles(["admin"]),
    )


def test_a_broad_principal_is_genuinely_narrowed_by_a_restrictive_workflow_agent_and_tool() -> None:
    """The real property FR-018/ADR-0023 exist for: an `admin` principal
    can, in principle, do everything (`workflow:read`, `workflow:start`,
    `pack:read`, `pack:manage`, `secret:access`, `config:read`,
    `config:manage`) — but a workflow
    declaring only `workflow:start`, whose agent declares only
    `workflow:start`, invoking a tool that declares only
    `workflow:start`, must genuinely end up with *only* `workflow:start`
    as this invocation's effective permission set, not the principal's
    full grant."""
    context = _admin_context()
    assert context.permissions == frozenset(
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
        }
    )

    effective = narrow_permissions(
        context,
        workflow_permissions=frozenset({WORKFLOW_START}),
        agent_permissions=frozenset({WORKFLOW_START}),
        tool_permissions=frozenset({WORKFLOW_START}),
    )

    assert effective == frozenset({WORKFLOW_START})
    assert SECRET_ACCESS not in effective
    assert PACK_MANAGE not in effective


def test_a_permission_missing_at_any_single_hop_is_genuinely_dropped() -> None:
    """Narrowing is a hard intersection, not a majority vote — a
    permission absent from even one link in the chain must not survive,
    no matter how many other links grant it."""
    context = _admin_context()

    # Missing only at the workflow hop.
    effective = narrow_permissions(
        context,
        workflow_permissions=frozenset({WORKFLOW_START}),
        agent_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
        tool_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
    )
    assert PACK_MANAGE not in effective

    # Missing only at the tool hop.
    effective = narrow_permissions(
        context,
        workflow_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
        agent_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
        tool_permissions=frozenset({WORKFLOW_START}),
    )
    assert PACK_MANAGE not in effective


def test_a_workflow_agent_or_tool_can_never_grant_a_permission_the_principal_lacks() -> None:
    """The "no elevation path" half of ADR-0023: a permission the
    principal never had cannot be manufactured by a downstream
    declaration, no matter how permissive."""
    low_privilege_context = SecurityContext(
        principal=Principal(
            principal_id="viewer-1", principal_type=PrincipalType.USER, roles=frozenset({"viewer"})
        ),
        permissions=permissions_for_roles(["viewer"]),
    )
    assert low_privilege_context.permissions == frozenset({WORKFLOW_READ, EVALUATION_READ})

    effective = narrow_permissions(
        low_privilege_context,
        workflow_permissions=frozenset({WORKFLOW_READ, SECRET_ACCESS, PACK_MANAGE}),
        agent_permissions=frozenset({WORKFLOW_READ, SECRET_ACCESS, PACK_MANAGE}),
        tool_permissions=frozenset({WORKFLOW_READ, SECRET_ACCESS, PACK_MANAGE}),
    )

    assert effective == frozenset({WORKFLOW_READ})
    assert SECRET_ACCESS not in effective


def test_narrowing_a_second_time_never_widens_the_already_effective_set() -> None:
    """Authority only ever shrinks — applying the narrowing chain again
    with a further, independent restriction can only keep it the same
    size or shrink it further, never grow it back."""
    context = _admin_context()
    first_pass = narrow_permissions(
        context,
        workflow_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
        agent_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
        tool_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
    )
    assert first_pass == frozenset({WORKFLOW_START, PACK_MANAGE})

    second_pass = narrow_permissions(
        context,
        workflow_permissions=first_pass,
        agent_permissions=frozenset({WORKFLOW_START}),
        tool_permissions=frozenset({WORKFLOW_START, PACK_MANAGE}),
    )

    assert second_pass == frozenset({WORKFLOW_START})
    assert second_pass <= first_pass


def test_is_permitted_answers_the_single_permission_question_the_full_chain_implies() -> None:
    context = _admin_context()

    assert is_permitted(
        context,
        WORKFLOW_START,
        workflow_permissions=frozenset({WORKFLOW_START}),
        agent_permissions=frozenset({WORKFLOW_START}),
        tool_permissions=frozenset({WORKFLOW_START}),
    )
    assert not is_permitted(
        context,
        SECRET_ACCESS,
        workflow_permissions=frozenset({WORKFLOW_START}),
        agent_permissions=frozenset({WORKFLOW_START}),
        tool_permissions=frozenset({WORKFLOW_START}),
    )


def test_an_empty_declaration_anywhere_in_the_chain_yields_no_effective_permissions() -> None:
    """A workflow/agent/tool that declares no permissions at all grants
    nothing to narrow into — an honest empty set, never a default-allow
    (ADR-0023: "absence of a permission is denial, never a default-
    allow")."""
    context = _admin_context()

    effective = narrow_permissions(
        context,
        workflow_permissions=frozenset(),
        agent_permissions=frozenset({WORKFLOW_START}),
        tool_permissions=frozenset({WORKFLOW_START}),
    )

    assert effective == frozenset()
