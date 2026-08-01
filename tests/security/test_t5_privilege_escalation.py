"""T5 — Privilege escalation across the invocation chain
(security_architecture.md §4/§9). Real defenses exercised here: deny by
default, no runtime elevation — §9's own words. Two real mechanisms:

1. :func:`~ai_os_kernel.security_manager.permissions.permissions_for_roles`
   grants nothing for an unrecognised/forged role — a principal cannot
   escalate simply by presenting a role string the system has never
   modelled.
2. :class:`~ai_os_kernel.secrets_manager.access_broker.AccessBroker`
   refuses (and audits) an access attempt from a principal whose real,
   role-derived permissions do not include it — and never even consults
   the underlying provider, so a denied attempt cannot accidentally
   reveal anything while being denied.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_os_kernel.observability.audit import AuditOutcome
from ai_os_kernel.secrets_manager.access_broker import AccessBroker
from ai_os_kernel.secrets_manager.errors import AccessDeniedError
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.permissions import SECRET_ACCESS, permissions_for_roles


class _FakeAuditLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        event_type: str,
        principal_id: str,
        principal_type: str,
        outcome: AuditOutcome,
        detail: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.records.append({"event_type": event_type, "outcome": outcome})


class _ExplodingProvider:
    """A stand-in that proves the denial happens before any resolution
    attempt — a real escalation would need the provider to ever be
    consulted at all."""

    async def resolve(self, reference: str) -> None:
        raise AssertionError("a denied access must never reach the real provider")


def test_presenting_a_forged_or_unmodelled_role_grants_no_permissions() -> None:
    """The real escalation attempt: a principal presents a role string
    the system has never granted anything to (e.g. a forged
    `super-admin`, or a typo'd real role hoping for a fail-open bug).
    Deny by default means an unrecognised role contributes nothing."""
    granted = permissions_for_roles(["super-admin", "root", "system"])

    assert granted == frozenset()


def test_a_low_privilege_role_can_never_reach_secret_access_by_construction() -> None:
    """Monotonic narrowing / no runtime elevation: `viewer` never gets
    `secret:access` no matter how many other (real or forged) roles are
    layered alongside it, since only the documented, hand-verified grant
    table can ever produce that permission."""
    granted = permissions_for_roles(["viewer", "not-a-real-role"])

    assert SECRET_ACCESS not in granted


@pytest.mark.asyncio
async def test_a_real_privilege_escalation_attempt_against_the_access_broker_is_denied() -> None:
    """An end-to-end attempt: a `viewer`-role principal (real,
    role-derived permissions, not a forged `SecurityContext`) tries to
    resolve a secret it was never granted. The broker must refuse it,
    audit the refusal as a real security event, and never touch the
    underlying provider."""
    viewer_context = SecurityContext(
        principal=Principal(
            principal_id="attacker-controlled-viewer",
            principal_type=PrincipalType.USER,
            roles=frozenset({"viewer"}),
        ),
        permissions=permissions_for_roles(["viewer"]),
    )
    audit_log = _FakeAuditLog()
    broker = AccessBroker(provider=_ExplodingProvider(), audit_log=audit_log)  # type: ignore[arg-type]

    with pytest.raises(AccessDeniedError):
        await broker.resolve("secret://env/llm-api-key", context=viewer_context)

    assert len(audit_log.records) == 1
    assert audit_log.records[0]["event_type"] == "secret.access.denied"
    assert audit_log.records[0]["outcome"] == AuditOutcome.DENIED
