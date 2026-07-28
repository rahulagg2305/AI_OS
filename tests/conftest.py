"""Session-wide test fixtures.

Shuts down the OpenTelemetry ``MeterProvider``'s background export
thread at the end of the test session.
:func:`ai_os_kernel.observability.metrics.configure_metrics` installs a
real ``PeriodicExportingMetricReader`` (a background thread) the first
time any test calls it — directly, or indirectly via
``bootstrap.build_app()`` — and without an explicit shutdown that
thread can attempt one more export after pytest has already closed the
streams it captured, producing a spurious
``ValueError: I/O operation on closed file`` traceback after an
otherwise clean, fully-passing test run.
"""

from collections.abc import Generator

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider


@pytest.fixture(scope="session", autouse=True)
def _shutdown_otel_meter_provider() -> Generator[None, None, None]:
    yield
    provider = metrics.get_meter_provider()
    if isinstance(provider, MeterProvider):
        provider.shutdown()
