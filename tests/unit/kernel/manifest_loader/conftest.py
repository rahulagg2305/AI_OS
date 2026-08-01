"""Shared fixture for entry-point-discovery tests: a real directory on
``sys.path`` that :mod:`importlib.metadata` genuinely scans for
installed distributions — a real integration fixture, not a mock of
``importlib.metadata`` itself. Shared by ``test_discovery.py`` and
``test_loader.py``.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from ai_os_kernel.manifest_loader.discovery import ENTRY_POINT_GROUP

DIST_INFO = "fake_pack-1.0.0.dist-info"
UNLOADABLE_TARGET = "fake_pack_module_that_does_not_actually_exist"


def write_dist_info(
    site: Path, *, entry_point_value: str = UNLOADABLE_TARGET, include_manifest: bool = True
) -> None:
    dist_info = site / DIST_INFO
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fake-pack\nVersion: 1.0.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{ENTRY_POINT_GROUP}]\nfake_pack = {entry_point_value}\n", encoding="utf-8"
    )
    record_lines = [
        f"{DIST_INFO}/METADATA,,",
        f"{DIST_INFO}/entry_points.txt,,",
        f"{DIST_INFO}/RECORD,,",
    ]
    if include_manifest:
        record_lines.insert(0, "manifest.yaml,,")
        (site / "manifest.yaml").write_text("apiVersion: ai-os/v1\n", encoding="utf-8")
    (dist_info / "RECORD").write_text("\n".join(record_lines) + "\n", encoding="utf-8")


@pytest.fixture
def site(tmp_path: Path) -> Generator[Path, None, None]:
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    sys.path.insert(0, str(site_dir))
    importlib.invalidate_caches()
    try:
        yield site_dir
    finally:
        sys.path.remove(str(site_dir))
        importlib.invalidate_caches()
