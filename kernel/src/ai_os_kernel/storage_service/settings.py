"""The one setting the local artifact store needs from the environment.

``AIOS_STORAGE_ROOT`` follows the identical "bootstrap-minimum,
``AIOS_``-prefixed, read directly" shape
:class:`~ai_os_kernel.caching.settings.RedisSettings`/
:class:`~ai_os_kernel.persistence.settings.DatabaseSettings` already
establish. Unlike ``AIOS_DATABASE_URL``, a missing value is not an
error: nothing in a real Kernel composition constructs
:class:`~ai_os_kernel.storage_service.local_store.LocalFilesystemArtifactStore`
yet, so a safe, real default keeps this settings class usable on its
own, the identical reasoning
:class:`~ai_os_kernel.caching.settings.RedisSettings` already
establishes for ``redis_url``.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

# A first-cut, not-yet-tuned default (coding_standards.md) — relative
# to the process's working directory, so a real local run and a real
# test run against a real, isolated `tmp_path` root never collide.
DEFAULT_STORAGE_ROOT = "data/artifacts"


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    storage_root: str = DEFAULT_STORAGE_ROOT
    """Directory :class:`~ai_os_kernel.storage_service.local_store.
    LocalFilesystemArtifactStore` writes content-addressed artifacts
    under."""
