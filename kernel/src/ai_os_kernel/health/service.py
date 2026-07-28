"""Aggregates component health into one readiness report.

Each check is a small callable returning a ``ComponentStatus``. Adding a
new component's readiness check means adding one entry to the list
passed to :class:`HealthService` — this class never changes.

Per docs/03_architecture/kernel/health_lifecycle.md: "A degraded state
should be reported rather than presenting an unhealthy system as
healthy." A component that is not fully "ok" makes the overall status
"degraded", not "ready" — but Stage A has no dependency whose failure
should make the Kernel refuse to serve entirely, so this never returns
a harder "not ready" state yet. That is added once a hard dependency
(e.g. the database) exists to justify it.
"""

from collections.abc import Callable

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    name: str
    status: str
    """One of: "ok", "degraded", "error"."""
    detail: str = ""


class ReadinessReport(BaseModel):
    status: str
    """One of: "ready", "degraded"."""
    components: list[ComponentStatus]


ComponentCheck = Callable[[], ComponentStatus]


class HealthService:
    def __init__(self, checks: list[ComponentCheck]) -> None:
        self._checks = checks

    def readiness(self) -> ReadinessReport:
        components = [check() for check in self._checks]
        overall = "ready" if all(c.status == "ok" for c in components) else "degraded"
        return ReadinessReport(status=overall, components=components)
