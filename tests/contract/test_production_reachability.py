"""An executable guard for risk-register **R-018** ("proven but idle":
real, tested subsystems with zero production reachability).

**Why this file exists.** R-018 has been re-derived by hand three times
(2026-08-11, twice; 2026-08-12) and got the answer wrong once — the
2026-08-11 sweep counted importers per *package*, so it reported
`event_bus` as reachable while two modules inside it were dead, and the
Outbox Relay stayed invisible for another day. Every one of those sweeps
was a `grep` whose result lived only in prose. Prose cannot fail a build,
so the disclosure could drift from the code silently in either direction:
a package could be quietly wired (making the docs overstate the gap) or a
newly-idle package could appear (making them understate it).

This test turns the disclosure into a checked invariant. It parses real
``import`` statements with :mod:`ast` rather than grepping, because every
previous sweep's false positives were docstring cross-references
(``:class:`~ai_os_kernel.caching.response_cache.ResponseCache```) that
look exactly like imports to a regular expression and are not imports at
all.

**It fails in both directions, deliberately.** Wiring one of the listed
packages into production is *good news* — and it still fails this test,
because the accompanying documentation is then wrong and must be updated
in the same step. That is the point: R-018's real defect was never the
idleness itself, it was that the idleness was invisible.

Scope note: this is a *package*-granularity guard, and R-018 item 8 is
the recorded proof that package granularity alone is insufficient. It is
not claimed to be a complete R-018 detector — it is a regression lock on
the five specific packages the audit named, which is exactly what those
five previously lacked.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every real production source tree. Deliberately excludes `tests/` —
# these packages all have real, passing tests; being tested is precisely
# what makes "proven but idle" the interesting state rather than a
# simple case of unfinished code.
PRODUCTION_ROOTS = (
    REPO_ROOT / "kernel" / "src",
    REPO_ROOT / "capability_packs",
    REPO_ROOT / "platform_sdk" / "src",
)

# The five packages risk register R-018 item 7 names, re-verified as
# genuinely idle on 2026-08-13. Each is real, tested code that no
# production composition constructs. See the risk register for the
# per-package reasoning on why each remains disclosed rather than wired.
KNOWN_IDLE_PACKAGES = frozenset(
    {
        "caching",
        "document_processing",
        "memory_manager",
        "speech_gateway",
        "storage_service",
    }
)


def _imported_kernel_packages(source_file: Path) -> set[str]:
    """Every ``ai_os_kernel.<package>`` named by a real ``import`` or
    ``from ... import`` statement in one file — nothing else. A module
    that fails to parse is a real problem for other tests to report, not
    something to swallow here, so no ``try`` around :func:`ast.parse`."""
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    packages: set[str] = set()
    for node in ast.walk(tree):
        dotted_names: list[str] = []
        if isinstance(node, ast.Import):
            dotted_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            dotted_names = [node.module]
        for dotted in dotted_names:
            parts = dotted.split(".")
            if len(parts) >= 2 and parts[0] == "ai_os_kernel":
                packages.add(parts[1])
    return packages


def _production_importers(package: str) -> set[Path]:
    """Real production files importing ``package``, excluding the
    package's own modules — a package importing itself says nothing
    about whether anything else can reach it."""
    own_prefix = REPO_ROOT / "kernel" / "src" / "ai_os_kernel" / package
    importers: set[Path] = set()
    for root in PRODUCTION_ROOTS:
        if not root.is_dir():
            continue
        for source_file in root.rglob("*.py"):
            if own_prefix in source_file.parents:
                continue
            # `capability_packs/*/tests/` sits *inside* a production
            # root, so excluding the top-level `tests/` tree is not
            # enough — a pack's own test importing a package would
            # otherwise read as production reachability, the exact
            # false positive this guard exists to eliminate. Caught by
            # the negative-control run, not assumed.
            if "tests" in source_file.relative_to(REPO_ROOT).parts:
                continue
            if package in _imported_kernel_packages(source_file):
                importers.add(source_file.relative_to(REPO_ROOT))
    return importers


def test_the_production_roots_this_guard_sweeps_really_exist() -> None:
    """A guard that silently sweeps nothing would pass forever. Assert
    the trees are real and non-trivial before trusting any result below
    — `capability_packs/` and `platform_sdk/src/` are both real on disk,
    unlike the many planned-but-absent folders `folder_structure.md`
    documents."""
    for root in PRODUCTION_ROOTS:
        assert root.is_dir(), f"production root {root} does not exist"
        assert any(root.rglob("*.py")), f"production root {root} contains no Python at all"


def test_this_guard_detects_a_package_that_is_genuinely_wired() -> None:
    """Proves the detector actually detects, rather than returning an
    empty set for everything. ``workflow_engine`` is unambiguously wired
    — ``bootstrap.py`` and the real routes import it — so a sweep that
    cannot see it is broken, and every "zero importers" result below
    would be worthless."""
    importers = _production_importers("workflow_engine")
    assert len(importers) > 1, (
        "the reachability sweep found almost no importers of a package known to be "
        f"heavily wired, so it is not working: {sorted(importers)}"
    )


def test_every_known_idle_package_is_still_genuinely_idle() -> None:
    """R-018 item 7's own claim, re-executed rather than re-asserted.

    If this fails because a package gained a real production importer,
    that is genuine progress — update the risk register and
    ``feature_inventory.md``, then remove it from
    ``KNOWN_IDLE_PACKAGES``. Do not weaken this assertion to make it
    pass."""
    still_idle: dict[str, set[Path]] = {}
    for package in sorted(KNOWN_IDLE_PACKAGES):
        importers = _production_importers(package)
        if importers:
            still_idle[package] = importers
    assert not still_idle, (
        "a package documented as having zero production reachability now has real "
        f"production importers: { {k: sorted(map(str, v)) for k, v in still_idle.items()} }. "
        "This is good news — update risk register R-018 and feature_inventory.md in the "
        "same step, then drop it from KNOWN_IDLE_PACKAGES."
    )


def test_every_known_idle_package_actually_exists_on_disk() -> None:
    """The disclosure must name real packages. A renamed or deleted
    package would otherwise sit in the list forever, trivially "idle"
    and quietly meaningless."""
    for package in sorted(KNOWN_IDLE_PACKAGES):
        package_dir = REPO_ROOT / "kernel" / "src" / "ai_os_kernel" / package
        assert package_dir.is_dir(), (
            f"{package} is listed as a known-idle package but no longer exists on disk"
        )
