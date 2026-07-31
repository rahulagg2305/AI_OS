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

Not yet implemented: full OIDC (JWKS, issuer/audience validation),
service-account API keys as a distinct mechanism, the full ADR-0023
permission vocabulary and monotonic-narrowing chain (principal ∩
workflow ∩ agent ∩ tool — the "narrowing across principal -> workflow ->
agent -> tool" this module's own placeholder docstring once described;
building the full chain needs manifest-declared permissions on
workflows/agents/tools, which is Capability Manager territory not yet
built), role assignment/administration, and a ``governance.audit_log``
writer for authentication/authorization events (logged via structlog
only, for now).
"""

from ai_os_kernel.security_manager.dependencies import require_permission
from ai_os_kernel.security_manager.errors import InvalidTokenError, SecurityError
from ai_os_kernel.security_manager.models import Principal, PrincipalType, SecurityContext
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
    "permissions_for_roles",
    "require_permission",
]
