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
