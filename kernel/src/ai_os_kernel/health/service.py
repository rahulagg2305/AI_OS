"""Aggregates component health into one readiness report.

Each check is a small callable returning a ``ComponentStatus``, either
directly (synchronous — the original, still-supported shape) or as an
``Awaitable`` (asynchronous — added so a check can genuinely read real
state from a database, e.g. a discovered pack's real
``catalog.packs.state`` via
:meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.get_pack`,
which no synchronous callable can do). Adding a new component's
readiness check means adding one entry to the list passed to
:class:`HealthService` — this class never changes, and a check author
picks whichever shape it genuinely needs; nothing forces every check to
become async just because one does.

Per docs/03_architecture/kernel/health_lifecycle.md: "A degraded state
should be reported rather than presenting an unhealthy system as
healthy." A component that is not fully "ok" makes the overall status
"degraded", not "ready" — but Stage A has no dependency whose failure
should make the Kernel refuse to serve entirely, so this never returns
a harder "not ready" state yet. That is added once a hard dependency
(e.g. the database) exists to justify it.
"""

import inspect
from collections.abc import Awaitable, Callable

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


ComponentCheck = Callable[[], "ComponentStatus | Awaitable[ComponentStatus]"]


class HealthService:
    def __init__(self, checks: list[ComponentCheck]) -> None:
        self._checks = checks

    async def readiness(self) -> ReadinessReport:
        components: list[ComponentStatus] = []
        for check in self._checks:
            result = check()
            if inspect.isawaitable(result):
                result = await result
            components.append(result)
        overall = "ready" if all(c.status == "ok" for c in components) else "degraded"
        return ReadinessReport(status=overall, components=components)
