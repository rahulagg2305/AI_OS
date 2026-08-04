"""The one setting the Redis client needs from the environment.

``AIOS_REDIS_URL`` is one of the "bootstrap minimum" environment
variables (docs/03_architecture/services/configuration_management.md
§3.3) — read directly from the environment, never from a
configuration file, the identical reasoning
``AIOS_DATABASE_URL``/:class:`~ai_os_kernel.persistence.settings.DatabaseSettings`
already establishes. Unlike that field, a missing value is not an
error: caching is still 0% built and off by default
(feature_inventory.md §2.18), so ``None`` is the genuine default
today, not a placeholder for a value startup should refuse to proceed
without — the identical reasoning
:class:`~ai_os_kernel.observability.settings.ObservabilitySettings`
already establishes for ``OTEL_EXPORTER_OTLP_ENDPOINT``.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str | None = None
    """e.g. ``redis://localhost:6379/0``. ``None`` means no Redis is
    configured for this process — callers must check before calling
    :func:`~ai_os_kernel.caching.client.build_redis_client`."""
