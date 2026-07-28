"""Reads the small set of environment variables needed to bootstrap the
Configuration Manager itself.

``env`` and ``role`` decide *which* configuration files to read and
*which* process role to start — they cannot themselves come from those
files (a chicken-and-egg problem: you need to know the environment
before you can find its config). These are therefore the only
environment variables the platform reads directly; every other value
comes from a configuration file (docs/03_architecture/services/configuration_management.md §3.3,
docs/11_deployment/deployment_architecture.md §7).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BootstrapEnv(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    """Which environment configuration layer to load: local | dev | staging | production."""

    role: str = "api"
    """Which process role this instance runs: api | worker (ADR-0020)."""
