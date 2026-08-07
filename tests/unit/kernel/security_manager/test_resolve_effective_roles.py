"""Unit tests for
:func:`ai_os_kernel.security_manager.role_administration.resolve_effective_roles`
— the real union logic shared by ``ApprovalService.decide`` and the
general ``authenticate()`` dependency (``P07-S02-M14-T02``, "Full
five-role model"). A fake, in-memory :class:`RoleGrantRepository` is a
legitimate ADR-0004 substitute here: this function's own logic is pure
(one set union), and the real, persisted-storage behaviour is already
proven against Postgres in
``tests/integration/security_manager/test_role_administration.py``."""

from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.security_manager.role_administration import RoleGrant, resolve_effective_roles


class _FakeRoleGrantRepository:
    """Only ``active_roles_for`` is exercised here — ``grant``/``revoke``
    exist solely to satisfy the ``RoleGrantRepository`` Protocol's
    structural shape and are never called by this function."""

    def __init__(self, granted_roles: frozenset[str]) -> None:
        self._granted_roles = granted_roles

    async def active_roles_for(self, principal_id: str) -> frozenset[str]:
        return self._granted_roles

    async def grant(
        self, *, principal_id: str, role: str, granted_by: str, reason: str
    ) -> RoleGrant:
        raise NotImplementedError

    async def revoke(
        self, *, principal_id: str, role: str, revoked_by: str, reason: str
    ) -> RoleGrant:
        raise NotImplementedError


def _principal(roles: frozenset[str]) -> Principal:
    return Principal(principal_id="test-principal", principal_type=PrincipalType.USER, roles=roles)


async def test_a_none_repository_returns_the_principal_unchanged() -> None:
    principal = _principal(frozenset({"viewer"}))

    resolved = await resolve_effective_roles(principal, None)

    assert resolved is principal


async def test_no_persisted_grants_returns_the_principal_unchanged() -> None:
    principal = _principal(frozenset({"viewer"}))
    repository = _FakeRoleGrantRepository(frozenset())

    resolved = await resolve_effective_roles(principal, repository)

    assert resolved is principal


async def test_a_persisted_grant_disjoint_from_the_tokens_own_roles_is_unioned_in() -> None:
    principal = _principal(frozenset({"viewer"}))
    repository = _FakeRoleGrantRepository(frozenset({"maintainer"}))

    resolved = await resolve_effective_roles(principal, repository)

    assert resolved.roles == frozenset({"viewer", "maintainer"})
    # The token's own claim is never mutated in place.
    assert principal.roles == frozenset({"viewer"})


async def test_a_persisted_grant_already_covered_by_the_tokens_own_roles_returns_it_unchanged() -> (
    None
):
    principal = _principal(frozenset({"admin"}))
    repository = _FakeRoleGrantRepository(frozenset({"admin"}))

    resolved = await resolve_effective_roles(principal, repository)

    assert resolved is principal
