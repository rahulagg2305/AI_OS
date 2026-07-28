"""The one setting persistence needs from the environment.

``AIOS_DATABASE_URL`` carries embedded credentials, so — like ``AIOS_ENV``
and ``AIOS_ROLE`` — it is read directly from the environment and never from
a configuration file (docs/03_architecture/services/configuration_management.md
§3.3). There is deliberately no default: a missing value must fail clearly
at startup rather than silently pointing nowhere.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    """SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host:5432/db."""
