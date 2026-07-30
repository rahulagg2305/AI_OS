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
"degraded", not "ready".

**§10's own "hard vs. soft dependency" gap is resolved (2026-07-30):
the database is a real hard dependency.** Every functional HTTP route
in this codebase (``POST /api/v1/workflows``,
``POST /api/v1/workflows/se.delivery_pipeline``,
``POST``/``GET /api/v1/packs*``) already independently returns ``503``
the moment its own required ``app.state`` object is absent because no
database is configured — confirmed by reading each route's own source,
not assumed. A component whose own ``critical`` field is ``True`` and
whose ``status`` is not ``"ok"`` therefore escalates the *overall*
report to a third state, ``"not_ready"`` — genuinely distinct from
``"degraded"`` — which :mod:`ai_os_kernel.routes.health` maps to HTTP
``503``, not ``200``: a Kubernetes readiness probe should stop routing
traffic to a Kernel instance where every functional route will 503
anyway, exactly per this document's own §7 rule ("Startup should not
advertise 'Ready' until critical components are functional"). Every
check written before this addition defaults ``critical=False`` and is
therefore unaffected — a non-critical failure still only ever produces
``"degraded"``, never ``"not_ready"``.
"""

import inspect
from collections.abc import Awaitable, Callable

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    name: str
    status: str
    """One of: "ok", "degraded", "error"."""
    detail: str = ""
    critical: bool = False
    """When True and status is not "ok", the overall report becomes
    "not_ready" rather than "degraded" — a hard dependency whose
    failure means the Kernel cannot serve meaningful traffic at all,
    not merely a reduced-capability one. Defaults to False so every
    check written before this field existed is unaffected."""


class ReadinessReport(BaseModel):
    status: str
    """One of: "ready", "degraded", "not_ready" (the last only when at
    least one critical component's status is not "ok")."""
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

        if any(c.critical and c.status != "ok" for c in components):
            overall = "not_ready"
        elif all(c.status == "ok" for c in components):
            overall = "ready"
        else:
            overall = "degraded"
        return ReadinessReport(status=overall, components=components)
