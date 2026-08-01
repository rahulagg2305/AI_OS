"""Entry-point pack discovery (``P01-S03-M02-T03``, ADR-0009's
production mechanism) — proven against a real, synthetic installed
distribution (a real ``*.dist-info`` directory placed on ``sys.path``
and discovered through the real :mod:`importlib.metadata`, via this
directory's own ``conftest.py``), not a mocked stand-in for it.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_kernel.manifest_loader.discovery import discover_entry_point_manifests
from tests.unit.kernel.manifest_loader.conftest import DIST_INFO, UNLOADABLE_TARGET, write_dist_info


def test_discovers_the_manifest_of_a_real_installed_distribution(site: Path) -> None:
    write_dist_info(site)

    discovered = list(discover_entry_point_manifests())

    assert discovered == [site / "manifest.yaml"]


def test_never_loads_the_entry_points_own_target(site: Path) -> None:
    """The entry point points at a module that genuinely does not
    exist and would raise ModuleNotFoundError if imported — discovery
    must still succeed, proving it never calls EntryPoint.load()
    (manifest_loader.md §6: the loader must not execute pack code)."""
    write_dist_info(site, entry_point_value=UNLOADABLE_TARGET)

    discovered = list(discover_entry_point_manifests())

    assert discovered == [site / "manifest.yaml"]


def test_a_distribution_with_no_manifest_is_skipped_not_raised(site: Path) -> None:
    write_dist_info(site, include_manifest=False)

    discovered = list(discover_entry_point_manifests())

    assert discovered == []


def test_an_unrelated_entry_point_group_is_ignored(site: Path) -> None:
    dist_info = site / DIST_INFO
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fake-pack\nVersion: 1.0.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        "[some.other.group]\nfake_pack = fake_pack_module\n", encoding="utf-8"
    )
    (dist_info / "RECORD").write_text(
        f"{DIST_INFO}/METADATA,,\n{DIST_INFO}/entry_points.txt,,\n{DIST_INFO}/RECORD,,\n",
        encoding="utf-8",
    )
    (site / "manifest.yaml").write_text("apiVersion: ai-os/v1\n", encoding="utf-8")

    discovered = list(discover_entry_point_manifests())

    assert discovered == []


def test_no_installed_distributions_yields_nothing(site: Path) -> None:
    assert list(discover_entry_point_manifests()) == []
