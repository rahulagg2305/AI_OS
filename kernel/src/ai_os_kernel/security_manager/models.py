"""The identity/authorization shapes ADR-0023 documents, reduced to
exactly what this step enforces: a principal's id, type, and roles
(:class:`Principal`), and the permissions computed from those roles for
one request (:class:`SecurityContext`) — the *principal* term of
ADR-0023's monotonic-narrowing intersection.

The narrowing computation itself (principal ∩ workflow ∩ agent ∩ tool)
now exists, real and tested — see
:mod:`ai_os_kernel.security_manager.narrowing`. What still does not
exist is a runtime source for the other three terms: no code anywhere
yet parses a workflow's/agent's/tool's declared ``permissions`` out of a
manifest (Capability Manager territory, not this module's). This class
still carries only the principal term for that reason, not because the
rest of the chain is unmodelled.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PrincipalType(StrEnum):
    """The two principal types that authenticate to the API — ``agent``
    never does (ADR-0023, api_architecture.md §4), so it has no place
    here."""

    USER = "user"
    SERVICE_ACCOUNT = "service_account"


class Principal(BaseModel):
    """One authenticated caller, as established by a
    :class:`~ai_os_kernel.security_manager.token_verifier.TokenVerifier`."""

    model_config = ConfigDict(frozen=True)

    principal_id: str
    principal_type: PrincipalType
    roles: frozenset[str]


class SecurityContext(BaseModel):
    """The authenticated principal plus its computed permissions for one
    request — the sole basis for an authorization decision
    (authentication_authorization.md §5)."""

    model_config = ConfigDict(frozen=True)

    principal: Principal
    permissions: frozenset[str]

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions
