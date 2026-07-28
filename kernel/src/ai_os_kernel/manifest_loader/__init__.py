"""Manifest Loader — discovers, validates, and registers Capability Packs.

Filesystem-scan discovery (ADR-0009's development mechanism) plus
schema-level validation against
``platform_sdk/schemas/manifest.schema.json``. Semantic validation
(kernel-version compatibility, global ID uniqueness, permission-subset
checks, resolving agent/tool/workflow references) is not implemented at
this stage.

See docs/03_architecture/kernel/manifest_loader.md.
"""

from ai_os_kernel.manifest_loader.errors import ManifestError
from ai_os_kernel.manifest_loader.loader import ManifestLoader
from ai_os_kernel.manifest_loader.models import (
    DiscoveredManifest,
    ManifestLoadFailure,
    ManifestScanReport,
    PackMetadata,
)

__all__ = [
    "DiscoveredManifest",
    "ManifestError",
    "ManifestLoadFailure",
    "ManifestLoader",
    "ManifestScanReport",
    "PackMetadata",
]
