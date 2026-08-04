"""Storage Service — content-addressed artifact storage
(feature_inventory.md §2.18): artifacts are referenced from workflow
state by a real ``sha256:<hex>`` id, never embedded in it.

Implemented so far (``P02-S07-M21-T01``): the local-filesystem backend
only (:class:`LocalFilesystemArtifactStore`, :class:`StorageSettings`).
No S3-compatible "prod" backend, no Protocol (a single real
implementation exists), and no real Kernel caller constructs this
store yet — workflow artifacts remain plain files in per-agent
temporary directories, unchanged by this step.
"""

from ai_os_kernel.storage_service.local_store import LocalFilesystemArtifactStore
from ai_os_kernel.storage_service.settings import DEFAULT_STORAGE_ROOT, StorageSettings

__all__ = [
    "DEFAULT_STORAGE_ROOT",
    "LocalFilesystemArtifactStore",
    "StorageSettings",
]
