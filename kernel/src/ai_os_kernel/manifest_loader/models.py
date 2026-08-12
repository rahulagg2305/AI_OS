"""Typed views over a loaded manifest.

These models are a convenience for calling code (health checks,
listings, tests) — they are **not** a replacement for the JSON Schema.
Schema-level validation is performed directly against
``platform_sdk/schemas/manifest.schema.json``; that file remains the
single authoritative structural contract.
"""

from typing import Any

from pydantic import BaseModel

from ai_os_kernel.manifest_loader.signature import ManifestSignatureResult


class PackMetadata(BaseModel):
    """The subset of ``manifest.metadata`` used at this stage."""

    id: str
    name: str
    version: str
    description: str
    owner: str


class DiscoveredManifest(BaseModel):
    """One manifest that was found and passed schema validation."""

    manifest_path: str
    metadata: PackMetadata
    raw: dict[str, Any]
    # Always populated (FR-117, `P01-S03-M28-T02`), including when
    # enforcement is off — the point is that the signing state of the
    # estate is observable *before* anyone turns enforcement on, rather
    # than discovered at the moment activation starts failing.
    signature: ManifestSignatureResult


class ManifestLoadFailure(BaseModel):
    """One manifest that was found but failed to load or validate."""

    manifest_path: str
    error: str


class ManifestScanReport(BaseModel):
    """The result of scanning every configured pack directory.

    Never raises for an individual bad manifest — each failure is
    captured here instead, so one broken pack cannot make discovery of
    every other pack impossible.
    """

    discovered: list[DiscoveredManifest]
    failed: list[ManifestLoadFailure]
