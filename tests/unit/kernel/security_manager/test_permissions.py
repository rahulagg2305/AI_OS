"""Unit tests for the role -> permission grants
(authentication_authorization.md §4.2, reduced to the permissions this
step models — see ai_os_kernel.security_manager.permissions)."""

from ai_os_kernel.security_manager.permissions import (
    CONFIG_MANAGE,
    CONFIG_READ,
    EVALUATION_READ,
    PACK_MANAGE,
    PACK_READ,
    SECRET_ACCESS,
    WORKFLOW_READ,
    WORKFLOW_START,
    permissions_for_roles,
)


def test_viewer_can_read_but_not_start_workflows() -> None:
    permissions = permissions_for_roles(["viewer"])

    assert permissions == frozenset({WORKFLOW_READ, EVALUATION_READ})


def test_operator_can_read_and_start_workflows() -> None:
    permissions = permissions_for_roles(["operator"])

    assert permissions == frozenset({WORKFLOW_READ, WORKFLOW_START, EVALUATION_READ})


def test_approver_can_read_but_not_start_workflows() -> None:
    permissions = permissions_for_roles(["approver"])

    assert permissions == frozenset({WORKFLOW_READ, EVALUATION_READ})


def test_maintainer_and_admin_can_read_and_start_workflows() -> None:
    assert permissions_for_roles(["maintainer"]) == frozenset(
        {
            WORKFLOW_READ,
            WORKFLOW_START,
            PACK_READ,
            PACK_MANAGE,
            CONFIG_READ,
            CONFIG_MANAGE,
            EVALUATION_READ,
        }
    )
    assert permissions_for_roles(["admin"]) == frozenset(
        {
            WORKFLOW_READ,
            WORKFLOW_START,
            PACK_READ,
            PACK_MANAGE,
            SECRET_ACCESS,
            CONFIG_READ,
            CONFIG_MANAGE,
            EVALUATION_READ,
        }
    )


def test_every_real_role_can_read_evaluation_data() -> None:
    """authentication_authorization.md §4.2's own `viewer` grant
    explicitly names "experiments, gate results" — every role includes
    at least `viewer`'s own grants, so every role gets this too."""
    for role in ("viewer", "operator", "approver", "maintainer", "admin"):
        assert EVALUATION_READ in permissions_for_roles([role])


def test_only_maintainer_and_admin_can_read_or_manage_packs() -> None:
    for role in ("viewer", "operator", "approver"):
        permissions = permissions_for_roles([role])
        assert PACK_READ not in permissions
        assert PACK_MANAGE not in permissions

    for role in ("maintainer", "admin"):
        permissions = permissions_for_roles([role])
        assert PACK_READ in permissions
        assert PACK_MANAGE in permissions


def test_only_maintainer_and_admin_can_read_or_manage_config() -> None:
    for role in ("viewer", "operator", "approver"):
        permissions = permissions_for_roles([role])
        assert CONFIG_READ not in permissions
        assert CONFIG_MANAGE not in permissions

    for role in ("maintainer", "admin"):
        permissions = permissions_for_roles([role])
        assert CONFIG_READ in permissions
        assert CONFIG_MANAGE in permissions


def test_only_admin_can_access_secrets() -> None:
    for role in ("viewer", "operator", "approver", "maintainer"):
        assert SECRET_ACCESS not in permissions_for_roles([role])

    assert SECRET_ACCESS in permissions_for_roles(["admin"])


def test_multiple_roles_union_their_permissions() -> None:
    permissions = permissions_for_roles(["viewer", "operator"])

    assert permissions == frozenset({WORKFLOW_READ, WORKFLOW_START, EVALUATION_READ})


def test_an_unrecognised_role_grants_nothing_rather_than_raising() -> None:
    permissions = permissions_for_roles(["not-a-real-role"])

    assert permissions == frozenset()


def test_no_roles_grants_nothing() -> None:
    assert permissions_for_roles([]) == frozenset()
