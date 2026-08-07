"""The fully resolved Kernel configuration.

Fields exist only once something reads them — an unused field is dead
configuration (Coding Standards: no speculative fields).
"""

from pydantic import BaseModel, ConfigDict, Field


class PlatformConfig(BaseModel):
    """Immutable, fully resolved configuration for one Kernel process.

    ``env`` and ``role`` are bootstrap identity — how this process was
    started — never values a configuration file may set. They are
    always supplied explicitly by
    :class:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager`,
    not read from YAML (see
    ``docs/03_architecture/services/configuration_management.md`` §3.3).
    """

    model_config = ConfigDict(frozen=True)

    env: str
    role: str

    host: str = "127.0.0.1"
    """Bind address for the API role. Secure default; overridden per environment for containers."""

    port: int = 8000

    log_level: str = "INFO"

    capability_pack_dirs: list[str] = Field(default_factory=lambda: ["capability_packs"])
    """Directories scanned for Capability Packs (filesystem-scan discovery, ADR-0009)."""

    manifest_schema_path: str = "platform_sdk/schemas/manifest.schema.json"
    """Path to the authoritative manifest JSON Schema, relative to the repository root."""

    pack_health_poll_interval_seconds: float | None = None
    """Overrides :data:`ai_os_kernel.capability_manager.health_poller.POLL_INTERVAL_SECONDS`
    for the real background polling loop (`ai_os_kernel.bootstrap._lifespan`).
    ``None`` (the default, every real deployment) means "use the real,
    decided policy constant" — this field exists only so a test can run
    the loop against a short interval without waiting out the real
    30-second production cadence; it is not itself a second policy
    decision."""

    lease_reap_interval_seconds: float | None = None
    """Overrides :data:`ai_os_kernel.workflow_engine.lease_reaper.LEASE_REAP_INTERVAL_SECONDS`
    for the real background lease-reap loop (`ai_os_kernel.bootstrap._lifespan`).
    The identical "test-only override, never a second policy decision"
    shape ``pack_health_poll_interval_seconds`` already establishes —
    ``None`` (every real deployment) means "use the real, decided
    15-second policy constant"."""

    audit_chain_verification_interval_seconds: float | None = None
    """Overrides
    :data:`ai_os_kernel.observability.audit_verification_job.AUDIT_CHAIN_VERIFICATION_INTERVAL_SECONDS`
    for the real background audit-chain verification loop
    (`ai_os_kernel.bootstrap._lifespan`). The identical "test-only
    override, never a second policy decision" shape
    ``lease_reap_interval_seconds`` already establishes — ``None``
    (every real deployment) means "use the real, decided 300-second
    policy constant"."""

    worker_poll_interval_seconds: float | None = None
    """Overrides :data:`ai_os_kernel.workflow_engine.worker_loop.WORKER_POLL_INTERVAL_SECONDS`
    for the real background multi-instance worker loop
    (`ai_os_kernel.bootstrap._lifespan`, `P02-S01-M05-T14`). The
    identical "test-only override, never a second policy decision"
    shape ``lease_reap_interval_seconds`` already establishes —
    ``None`` (every real deployment) means "use the real, decided
    5-second policy constant"."""

    scheduler_interval_seconds: float | None = None
    """Overrides :data:`ai_os_kernel.workflow_engine.scheduler.SCHEDULER_INTERVAL_SECONDS`
    for the real background Scheduler loop (`ai_os_kernel.bootstrap._lifespan`,
    `P02-S01-M05-T13`). The identical "test-only override, never a
    second policy decision" shape ``lease_reap_interval_seconds``
    already establishes — ``None`` (every real deployment) means "use
    the real, decided 5-second policy constant"."""

    # No `otlp_endpoint` field here: `OTEL_EXPORTER_OTLP_ENDPOINT` is one
    # of §3.3's named "bootstrap minimum" environment variables, read
    # directly (`ai_os_kernel.observability.settings.ObservabilitySettings`),
    # the identical reasoning `AIOS_DATABASE_URL`/`DatabaseSettings`
    # already establishes — never a `PlatformConfig`/YAML value.

    oidc_issuer: str | None = None
    """The real OIDC provider's issuer URL (ADR-0023: "user | OIDC
    bearer token"; `P07-S02-M14-T01`). ``None`` (every current
    environment, since no real provider has been configured anywhere
    yet) means `ai_os_kernel.bootstrap._build_token_verifier` falls
    back to the pre-shared-secret `JWTBearerTokenVerifier` unchanged —
    all three OIDC fields must be present together for the real
    `OidcBearerTokenVerifier` to be selected."""

    oidc_audience: str | None = None
    """The audience this Kernel process expects a real OIDC-issued
    token to carry. See ``oidc_issuer`` for the "all three together"
    selection rule."""

    oidc_jwks_uri: str | None = None
    """The real OIDC provider's JWKS endpoint — fetched (and cached) by
    :class:`jwt.PyJWKClient` inside `OidcBearerTokenVerifier`, never
    parsed by hand. See ``oidc_issuer`` for the "all three together"
    selection rule."""
