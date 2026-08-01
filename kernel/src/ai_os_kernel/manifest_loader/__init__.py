"""Manifest Loader — discovers, validates, and registers Capability Packs.

Both ADR-0009 discovery mechanisms are real: filesystem scan (the
development mechanism) and, as of ``P01-S03-M02-T03``, entry-point
discovery via the ``ai_os.capability_packs`` group (the production
mechanism, for packs installed from outside the repository) — plus
schema-level validation against
``platform_sdk/schemas/manifest.schema.json``. Semantic validation
(kernel-version compatibility, global ID uniqueness, permission-subset
checks, resolving agent/tool/workflow references) is not implemented at
this stage.

See docs/03_architecture/kernel/manifest_loader.md.
"""

from ai_os_kernel.manifest_loader.discovery import (
    ENTRY_POINT_GROUP,
    discover_entry_point_manifests,
)
from ai_os_kernel.manifest_loader.errors import ManifestError
from ai_os_kernel.manifest_loader.loader import ManifestLoader
from ai_os_kernel.manifest_loader.models import (
    DiscoveredManifest,
    ManifestLoadFailure,
    ManifestScanReport,
    PackMetadata,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "DiscoveredManifest",
    "ManifestError",
    "ManifestLoadFailure",
    "ManifestLoader",
    "ManifestScanReport",
    "PackMetadata",
    "discover_entry_point_manifests",
]
