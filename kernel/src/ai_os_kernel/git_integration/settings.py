"""The real config source for the Git Integration Service's own
deployment-specific values — remote URL, author identity, protected
branches (``git_integration.md``'s own disclosed "no Configuration-
Manager-sourced repository URLs or protected-branch policy yet" gap,
closed here).

Read directly from the environment via ``AIOS_GIT_*`` — never
``PlatformConfig``/YAML. This follows the identical reasoning
``configuration_manager/models.py`` already states for
``OTEL_EXPORTER_OTLP_ENDPOINT``/``ObservabilitySettings`` and
``AIOS_DATABASE_URL``/``DatabaseSettings``: a repository's real push
destination and author identity are deployment-specific values, not a
tunable policy constant ``PlatformConfig``'s own fields already cover.

Like :class:`~ai_os_kernel.observability.settings.ObservabilitySettings`
(and unlike :class:`~ai_os_kernel.persistence.settings.DatabaseSettings`),
every field here defaults to ``None`` — no remote is configured in any
environment yet, so ``None`` is the genuine default, not a placeholder
for a value startup should refuse to proceed without.
:func:`~ai_os_kernel.git_integration.default_service.
build_git_integration_service_from_env` is what enforces the "if a
remote *is* configured, author identity and protected branches must be
real too" rule — a concern deliberately kept out of this settings class,
which only ever reads and parses.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class GitIntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOS_GIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    remote_url: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    protected_branches: str | None = None
    """Comma-separated branch names, e.g. ``"main,release"`` —
    :class:`~ai_os_kernel.git_integration.models.GitPushPolicy` itself
    wants a ``frozenset[str]``, but env vars only ever carry strings."""
