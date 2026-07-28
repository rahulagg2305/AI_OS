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
