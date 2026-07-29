#!/usr/bin/env python
"""CI entry point for ``pack_contract_suite`` check 7
(``platform_sdk_v1_scope.md`` step 8) — the "no forbidden imports" rule
(``platform_sdk.md`` §9 item 7). Referenced by ``.github/workflows/ci.yml``'s
own pre-existing, gated `contract` job step: that step already runs
whenever this file exists (``hashFiles('scripts/check_import_boundaries.py')
!= ''``), so creating this file is the entire CI wiring — no workflow
edit needed.

**Discovers every real Capability Pack, not one hardcoded path.** A
pack is any direct child of ``capability_packs/`` that has both a
``pyproject.toml`` and a ``src/`` directory — the same two facts that
make it a real, buildable Python distribution at all. This is what "no
hardcoded values" means here: the one real pack today
(``software-engineering``) is discovered, not named in this script, so
a second real pack is checked automatically the day it exists, with no
change to this file.

**A pack's own top-level package name is read from its own
``pyproject.toml``**, not guessed from its directory name (which uses a
hyphen — ``software-engineering`` — while the importable package uses
underscores — ``ai_os_pack_software_engineering``): the first entry in
``[tool.hatch.build.targets.wheel].packages`` is the canonical answer, and
every real pack's own ``pyproject.toml`` already declares it for the
wheel builder's sake.

**Exit code is the real gate.** Zero if every pack has zero *unwaived*
forbidden imports; non-zero otherwise — this is what makes the CI step
fail the build for a genuine violation while a documented, active waiver
lets the same run pass.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from ai_os_sdk.testing import apply_waiver, load_waiver, render_report, scan_pack_source

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKS_ROOT = _REPO_ROOT / "capability_packs"
_WAIVER_FILENAME = "pack_contract_waiver.yaml"


def _own_pack_package(pack_root: Path) -> str | None:
    pyproject_path = pack_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return None
    with pyproject_path.open("rb") as fh:
        pyproject = tomllib.load(fh)
    packages = (
        pyproject.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("packages", [])
    )
    if not packages:
        return None
    # "src/ai_os_pack_software_engineering" -> "ai_os_pack_software_engineering"
    return Path(packages[0]).name


def _discover_packs() -> list[Path]:
    if not _PACKS_ROOT.is_dir():
        return []
    return sorted(
        p
        for p in _PACKS_ROOT.iterdir()
        if p.is_dir() and (p / "pyproject.toml").is_file() and (p / "src").is_dir()
    )


def main() -> int:
    pack_roots = _discover_packs()
    if not pack_roots:
        print("No capability packs with a src/ tree found — nothing to check.")
        return 0

    exit_code = 0
    for pack_root in pack_roots:
        own_package = _own_pack_package(pack_root)
        if own_package is None:
            print(f"[SKIP] {pack_root.name}: could not determine its own package name.")
            continue

        print(f"=== check 7 (forbidden imports): {pack_root.name} ===")
        violations = scan_pack_source(pack_root / "src", own_pack_package=own_package)
        waiver = load_waiver(pack_root / _WAIVER_FILENAME)
        application = apply_waiver(violations, waiver)
        print(render_report(application))
        print()

        if application.unwaived:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
