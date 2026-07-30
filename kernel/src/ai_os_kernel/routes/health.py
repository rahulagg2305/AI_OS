"""Health and version endpoints.

See docs/03_architecture/kernel/health_lifecycle.md and
docs/07_api/api_architecture.md §6.7.

Readiness is backed by real component checks
(:class:`ai_os_kernel.health.HealthService`), not a hardcoded response.
"""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request, Response

from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.health import HealthService, ReadinessReport

_NOT_READY_STATUS_CODE = 503

router = APIRouter(prefix="/api/v1", tags=["health"])


def _package_version() -> str:
    """Read the installed distribution version rather than hard-coding it."""
    try:
        return version("ai-os-kernel")
    except PackageNotFoundError:
        return "0.0.0+unknown"


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness probe. Must never depend on an external service — a brief
    dependency blip must not cause a container restart (Deployment
    Architecture §6)."""
    return {"status": "live"}


@router.get("/health/ready", response_model=ReadinessReport)
async def health_ready(request: Request, response: Response) -> ReadinessReport:
    """Readiness probe. Returns HTTP 200 for "ready"/"degraded" — a
    reduced-capability Kernel can still usefully serve some traffic —
    and HTTP 503 for "not_ready": at least one critical component (the
    database, today — see ``ai_os_kernel.health.service``'s own
    docstring for why it is a real hard dependency, not an assumed one)
    has failed, and every functional route in this codebase already
    independently 503s without one anyway."""
    health_service: HealthService = request.app.state.health_service
    report = await health_service.readiness()
    if report.status == "not_ready":
        response.status_code = _NOT_READY_STATUS_CODE
    return report


def build_version_payload(config: PlatformConfig) -> dict[str, str]:
    """Pure function so the payload shape is unit-testable without an app."""
    return {
        "service": "ai-os-kernel",
        "version": _package_version(),
        "environment": config.env,
        "role": config.role,
    }


@router.get("/version")
async def get_version(request: Request) -> dict[str, str]:
    config: PlatformConfig = request.app.state.config
    return build_version_payload(config)
