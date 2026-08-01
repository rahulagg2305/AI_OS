"""Security Manager — minimal authentication + authorization slice.

See docs/03_architecture/kernel/security_manager.md,
docs/09_security/authentication_authorization.md, ADR-0023.

Implemented so far — exactly enough to safely front the Workflow Engine
routes (:mod:`ai_os_kernel.routes.workflows`) and the Capability
Manager's pack lifecycle routes (:mod:`ai_os_kernel.routes.packs`):

- :class:`Principal`/:class:`PrincipalType`/:class:`SecurityContext` —
  identity and computed-permissions shapes, reduced from ADR-0023's
  full model (see :mod:`ai_os_kernel.security_manager.models`).
- :func:`permissions_for_roles` — the role -> permission grants this
  step enforces (``workflow:read``, ``workflow:start``, ``pack:read``,
  ``pack:manage``, ``secret:access`` only; see
  :mod:`ai_os_kernel.security_manager.permissions`).
- :class:`TokenVerifier` (``Protocol``) / :class:`JWTBearerTokenVerifier`
  — bearer-token authentication via a pre-shared HS256 signing key, not
  full OIDC (see :mod:`ai_os_kernel.security_manager.token_verifier` for
  why, and for the documented OIDC upgrade path).
- :func:`require_permission` — the FastAPI dependency chain routes use
  to authenticate and authorize in one call (see
  :mod:`ai_os_kernel.security_manager.dependencies`).
- :func:`narrow_permissions`/:func:`is_permitted` — ADR-0023's monotonic
  narrowing intersection (principal ∩ workflow ∩ agent ∩ tool), real and
  tested (``P03-S05-M14-T03``; see
  :mod:`ai_os_kernel.security_manager.narrowing`). Not yet wired into a
  real invocation: nothing yet parses workflow/agent/tool declared
  permissions out of a manifest, so this computation has no real data
  to narrow against end to end — Capability Manager territory, still
  not built.

Not yet implemented: full OIDC (JWKS, issuer/audience validation),
service-account API keys as a distinct mechanism, the full ADR-0023
permission vocabulary, manifest-sourced workflow/agent/tool declared
permissions (see :func:`narrow_permissions`'s own docstring), role
assignment/administration, and a ``governance.audit_log`` writer for
authentication/authorization events (logged via structlog only, for
now).
"""

from ai_os_kernel.security_manager.dependencies import require_permission
from ai_os_kernel.security_manager.errors import InvalidTokenError, SecurityError
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
from ai_os_kernel.security_manager.narrowing import is_permitted, narrow_permissions
from ai_os_kernel.security_manager.permissions import (
    PACK_MANAGE,
    PACK_READ,
    SECRET_ACCESS,
    WORKFLOW_READ,
    WORKFLOW_START,
    permissions_for_roles,
)
from ai_os_kernel.security_manager.token_verifier import (
    JWTBearerTokenVerifier,
    TokenVerifier,
    build_jwt_bearer_token_verifier,
)

__all__ = [
    "PACK_MANAGE",
    "PACK_READ",
    "SECRET_ACCESS",
    "WORKFLOW_READ",
    "WORKFLOW_START",
    "InvalidTokenError",
    "JWTBearerTokenVerifier",
    "Principal",
    "PrincipalType",
    "SecurityContext",
    "SecurityError",
    "TokenVerifier",
    "build_jwt_bearer_token_verifier",
    "is_permitted",
    "narrow_permissions",
    "permissions_for_roles",
    "require_permission",
]
