"""Discovers, parses, and schema-validates Capability Pack manifests.

Fails closed for a single manifest requested directly
(:meth:`ManifestLoader.load_one`): an invalid manifest raises
``ManifestError`` and is never returned. :meth:`ManifestLoader.scan`
never raises — it is used for status/health reporting, where one
broken pack must not prevent discovering every other pack.

**:meth:`ManifestLoader.scan` combines both ADR-0009 discovery
mechanisms** (filesystem scan and entry-point discovery,
``P01-S03-M02-T03``) and validates whatever either finds through the
identical path — "both validated identically" is not vacuously true
now that a second mechanism exists. A path found by both (a pack
present in a configured directory *and* separately registered as an
installed distribution pointing at the same real file) is validated
once, not twice.

Semantic validation (kernel-version compatibility, global ID uniqueness
across packs, permission-subset checks, resolving agent/tool/workflow
references) is not implemented at this stage — see
docs/03_architecture/capability_framework/manifest_schema.md for the
full rule set this will eventually enforce.
"""

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ai_os_kernel.manifest_loader.discovery import (
    discover_entry_point_manifests,
    discover_manifests,
)
from ai_os_kernel.manifest_loader.errors import ManifestError
from ai_os_kernel.manifest_loader.models import (
    DiscoveredManifest,
    ManifestLoadFailure,
    ManifestScanReport,
    PackMetadata,
)


class ManifestLoader:
    def __init__(self, *, pack_dirs: list[str], schema_path: Path) -> None:
        self._pack_dirs = pack_dirs
        self._schema_path = schema_path
        self._validator = self._build_validator(schema_path)

    @staticmethod
    def _build_validator(schema_path: Path) -> Draft202012Validator:
        if not schema_path.is_file():
            raise ManifestError(f"Manifest schema not found at {schema_path}.")
        with schema_path.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def scan(self) -> ManifestScanReport:
        """Discover every manifest reachable by either ADR-0009
        mechanism — the configured pack directories (filesystem scan)
        and installed distributions (entry-point discovery) — and
        validate all of them through the identical path.

        Never raises: each individual failure is captured rather than
        aborting the scan. Used by health/status reporting and listings.
        """
        discovered: list[DiscoveredManifest] = []
        failed: list[ManifestLoadFailure] = []
        seen: set[Path] = set()
        candidates = (*discover_manifests(self._pack_dirs), *discover_entry_point_manifests())
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                discovered.append(self.load_one(path))
            except ManifestError as exc:
                failed.append(ManifestLoadFailure(manifest_path=str(path), error=str(exc)))
        return ManifestScanReport(discovered=discovered, failed=failed)

    def load_one(self, manifest_path: Path) -> DiscoveredManifest:
        """Parse and schema-validate a single manifest. Raises
        ``ManifestError`` with a clear reason on any failure."""
        raw = self._parse_yaml(manifest_path)
        self._validate_schema(manifest_path, raw)
        metadata = self._extract_metadata(manifest_path, raw)
        return DiscoveredManifest(manifest_path=str(manifest_path), metadata=metadata, raw=raw)

    def _parse_yaml(self, manifest_path: Path) -> dict[str, Any]:
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ManifestError(f"{manifest_path}: not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ManifestError(f"{manifest_path}: must contain a YAML mapping at the top level.")
        return data

    def _validate_schema(self, manifest_path: Path, raw: dict[str, Any]) -> None:
        errors = sorted(self._validator.iter_errors(raw), key=lambda e: list(map(str, e.path)))
        if not errors:
            return
        details = "\n".join(
            f"  - {'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        )
        raise ManifestError(f"{manifest_path} failed manifest schema validation:\n{details}")

    def _extract_metadata(self, manifest_path: Path, raw: dict[str, Any]) -> PackMetadata:
        try:
            return PackMetadata.model_validate(raw["metadata"])
        except Exception as exc:
            raise ManifestError(f"{manifest_path}: invalid 'metadata' section: {exc}") from exc
