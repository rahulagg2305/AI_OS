"""Health & Lifecycle — aggregates component health into a readiness report.

Distinct from ``ai_os_kernel.routes.health``, which is only the HTTP
surface that calls into this component.

**Graceful shutdown** (added 2026-08-01, ``P01-S04-M03-T06``) —
:class:`GracefulShutdownCoordinator` drains a process's background
loops (the Pack Health Collector poll, the Lease Reaper, the
audit-chain verification job) on shutdown, so none of them is
abruptly killed mid-step. See
:mod:`ai_os_kernel.health.shutdown`.

See docs/03_architecture/kernel/health_lifecycle.md.
"""

from ai_os_kernel.health.service import ComponentStatus, HealthService, ReadinessReport
from ai_os_kernel.health.shutdown import GracefulShutdownCoordinator

__all__ = ["ComponentStatus", "GracefulShutdownCoordinator", "HealthService", "ReadinessReport"]
