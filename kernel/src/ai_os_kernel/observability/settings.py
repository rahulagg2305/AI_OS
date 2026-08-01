"""The one setting OTLP export needs from the environment.

``OTEL_EXPORTER_OTLP_ENDPOINT`` is one of the "bootstrap minimum"
environment variables (docs/03_architecture/services/
configuration_management.md §3.3) — read directly from the
environment, never from a configuration file, the identical reasoning
``AIOS_DATABASE_URL``/:class:`~ai_os_kernel.persistence.settings.DatabaseSettings`
already establishes. Unlike that field, a missing value is not an
error: no Collector is deployed in any environment yet, so ``None``
(console exporters) is the genuine default, not a placeholder for a
value startup should refuse to proceed without.

Uses the OpenTelemetry SDK's own standard variable name, not an
``AIOS_``-prefixed one — so any OTel-aware tooling that already reads
this variable keeps working, and this platform does not invent a
second name for a concept the ecosystem already standardised.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    otlp_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT")
    )
    """Base OpenTelemetry Collector endpoint for OTLP/HTTP export (e.g.
    ``"http://localhost:4318"``), ADR-0017 — "The Collector, not
    application code, decides the real backend."
    :func:`ai_os_kernel.observability.tracing.configure_tracing`/
    :func:`ai_os_kernel.observability.metrics.configure_metrics` append
    each signal's own standard path (``v1/traces``/``v1/metrics``)."""
