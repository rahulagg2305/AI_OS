"""Unit tests for the identity/authorization shapes
(ai_os_kernel.security_manager.models)."""

from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext


def test_security_context_has_permission_reflects_its_computed_set() -> None:
    context = SecurityContext(
        principal=Principal(
            principal_id="user-1", principal_type=PrincipalType.USER, roles=frozenset({"viewer"})
        ),
        permissions=frozenset({"workflow:read"}),
    )

    assert context.has_permission("workflow:read")
    assert not context.has_permission("workflow:start")
