"""Unit tests for the Manifest Loader (discovery + schema validation)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.manifest_loader import ManifestError, ManifestLoader

SCHEMA_PATH = Path("platform_sdk/schemas/manifest.schema.json")

_VALID_MANIFEST: dict[str, Any] = {
    "apiVersion": "ai-os/v1",
    "kind": "CapabilityPack",
    "metadata": {
        "id": "example-pack",
        "name": "Example Pack",
        "version": "0.1.0",
        "description": "A fixture pack used only by unit tests.",
        "owner": "test-owner",
        "license": "UNLICENSED",
    },
    "compatibility": {"minKernelVersion": "0.1.0"},
    "dependencies": {"sdkVersion": ">=0.1.0,<1.0.0"},
}


def _write_manifest(pack_dir: Path, content: dict[str, Any]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.yaml").write_text(yaml.safe_dump(content), encoding="utf-8")


def test_scan_discovers_a_valid_manifest(tmp_path: Path) -> None:
    _write_manifest(tmp_path / "example-pack", _VALID_MANIFEST)
    loader = ManifestLoader(pack_dirs=[str(tmp_path)], schema_path=SCHEMA_PATH)

    report = loader.scan()

    assert len(report.discovered) == 1
    assert report.discovered[0].metadata.id == "example-pack"
    assert report.failed == []


def test_scan_separates_an_invalid_manifest_without_raising(tmp_path: Path) -> None:
    invalid = {**_VALID_MANIFEST, "metadata": dict(_VALID_MANIFEST["metadata"])}
    del invalid["metadata"]["owner"]  # required field missing
    _write_manifest(tmp_path / "broken-pack", invalid)

    loader = ManifestLoader(pack_dirs=[str(tmp_path)], schema_path=SCHEMA_PATH)
    report = loader.scan()

    assert report.discovered == []
    assert len(report.failed) == 1
    assert "owner" in report.failed[0].error


def test_load_one_raises_clearly_on_schema_violation(tmp_path: Path) -> None:
    invalid = {
        **_VALID_MANIFEST,
        "metadata": {**_VALID_MANIFEST["metadata"], "id": "Not A Valid Id"},
    }
    pack_dir = tmp_path / "bad-id"
    _write_manifest(pack_dir, invalid)

    loader = ManifestLoader(pack_dirs=[str(tmp_path)], schema_path=SCHEMA_PATH)

    with pytest.raises(ManifestError, match="id"):
        loader.load_one(pack_dir / "manifest.yaml")


def test_load_one_raises_clearly_on_invalid_yaml(tmp_path: Path) -> None:
    pack_dir = tmp_path / "bad-yaml"
    pack_dir.mkdir()
    (pack_dir / "manifest.yaml").write_text("key: [unterminated", encoding="utf-8")

    loader = ManifestLoader(pack_dirs=[str(tmp_path)], schema_path=SCHEMA_PATH)

    with pytest.raises(ManifestError):
        loader.load_one(pack_dir / "manifest.yaml")


def test_discover_skips_a_missing_pack_directory(tmp_path: Path) -> None:
    loader = ManifestLoader(pack_dirs=[str(tmp_path / "does-not-exist")], schema_path=SCHEMA_PATH)

    report = loader.scan()

    assert report.discovered == []
    assert report.failed == []


def test_missing_schema_file_fails_clearly_at_construction() -> None:
    with pytest.raises(ManifestError):
        ManifestLoader(pack_dirs=[], schema_path=Path("does/not/exist.json"))


def test_the_committed_template_pack_is_discovered_and_schema_valid() -> None:
    """Regression test on the real, shipped _template pack."""
    loader = ManifestLoader(pack_dirs=["capability_packs"], schema_path=SCHEMA_PATH)

    report = loader.scan()

    discovered_ids = {m.metadata.id for m in report.discovered}
    assert "template-pack" in discovered_ids
    assert report.failed == []
