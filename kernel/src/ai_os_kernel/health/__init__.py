"""Health & Lifecycle — aggregates component health into a readiness report.

Distinct from ``ai_os_kernel.routes.health``, which is only the HTTP
surface that calls into this component.

See docs/03_architecture/kernel/health_lifecycle.md.
"""

from ai_os_kernel.health.service import ComponentStatus, HealthService, ReadinessReport

__all__ = ["ComponentStatus", "HealthService", "ReadinessReport"]
