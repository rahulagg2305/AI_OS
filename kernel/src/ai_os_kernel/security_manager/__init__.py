"""Security Manager — minimal authentication + authorization slice.

See docs/03_architecture/kernel/security_manager.md,
docs/09_security/authentication_authorization.md, ADR-0023.

Implemented so far — exactly enough to safely front the Workflow Engine
routes (:mod:`ai_os_kernel.routes.workflows`), the Capability
Manager's pack lifecycle routes (:mod:`ai_os_kernel.routes.packs`), and
the Human Approval decide route (:mod:`ai_os_kernel.routes.approvals`):

- :class:`Principal`/:class:`PrincipalType`/:class:`SecurityContext` —
  identity and computed-permissions shapes, reduced from ADR-0023's
  full model (see :mod:`ai_os_kernel.security_manager.models`).
- :func:`permissions_for_roles` — the role -> permission grants this
  step enforces (``workflow:read``, ``workflow:start``, ``pack:read``,
  ``pack:manage``, ``secret:access`` only; see
  :mod:`ai_os_kernel.security_manager.permissions`).
- :class:`TokenVerifier` (``Protocol``) / :class:`JWTBearerTokenVerifier`
  (pre-shared HS256 signing key, the safe zero-config default) /
  :class:`OidcBearerTokenVerifier` (real, JWKS-based RS256 verification
  with issuer/audience validation, ``P07-S02-M14-T01``) — see
  :mod:`ai_os_kernel.security_manager.token_verifier` for the full
  reasoning behind keeping both.
- :func:`require_permission` — the FastAPI dependency chain routes use
  to authenticate and authorize in one call (see
  :mod:`ai_os_kernel.security_manager.dependencies`).
- :func:`authenticate` (``P03-S03-M30-T06``) — the bare, real
  Bearer/JWT authentication half of that same chain, exported directly
  for a route that needs no *flat* permission check because a
  resource-specific check already exists elsewhere (see
  :mod:`ai_os_kernel.security_manager.dependencies`'s own docstring for
  the real, concrete case — class-scoped ``approver:<class>`` roles —
  that makes this necessary, not merely convenient).
- :func:`narrow_permissions`/:func:`is_permitted` — ADR-0023's monotonic
  narrowing intersection (principal ∩ workflow ∩ agent ∩ tool), real and
  tested (``P03-S05-M14-T03``; see
  :mod:`ai_os_kernel.security_manager.narrowing`). Not yet wired into a
  real invocation: nothing yet parses workflow/agent/tool declared
  permissions out of a manifest, so this computation has no real data
  to narrow against end to end — Capability Manager territory, still
  not built.

Not yet implemented: service-account API keys as a distinct mechanism,
the full ADR-0023 permission vocabulary, and manifest-sourced
workflow/agent/tool declared permissions (see
:func:`narrow_permissions`'s own docstring). OIDC verification is real
(above); OIDC provider *administration* (registering/rotating a real
provider's config) is not — `oidc_issuer`/`oidc_audience`/
`oidc_jwks_uri` are plain `PlatformConfig` fields, not a managed
resource.
Role administration (grant/revoke ``approver:<class>``,
``P03-S05-M14-T07``/``T08``, HTTP-reachable) and its own audit trail
now exist too — see :mod:`ai_os_kernel.security_manager.
role_administration`; the rest of this module's authentication/
authorization events (plain bearer-token success/failure,
``require_permission()`` denials) remain structlog-only.
"""

from ai_os_kernel.security_manager.dependencies import authenticate, require_permission
from ai_os_kernel.security_manager.errors import InvalidTokenError, SecurityError
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.narrowing import is_permitted, narrow_permissions
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
from ai_os_kernel.security_manager.token_verifier import (
    JWTBearerTokenVerifier,
    OidcBearerTokenVerifier,
    TokenVerifier,
    build_jwt_bearer_token_verifier,
    build_oidc_bearer_token_verifier,
)

__all__ = [
    "CONFIG_MANAGE",
    "CONFIG_READ",
    "EVALUATION_READ",
    "PACK_MANAGE",
    "PACK_READ",
    "SECRET_ACCESS",
    "WORKFLOW_READ",
    "WORKFLOW_START",
    "InvalidTokenError",
    "JWTBearerTokenVerifier",
    "OidcBearerTokenVerifier",
    "Principal",
    "PrincipalType",
    "SecurityContext",
    "SecurityError",
    "TokenVerifier",
    "authenticate",
    "build_jwt_bearer_token_verifier",
    "build_oidc_bearer_token_verifier",
    "is_permitted",
    "narrow_permissions",
    "permissions_for_roles",
    "require_permission",
]
