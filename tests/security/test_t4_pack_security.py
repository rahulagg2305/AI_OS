"""T4 — Malicious/compromised Capability Pack (security_architecture.md
§4/§8). Real defense exercised here: the pack contract suite's "no
forbidden imports" check — a pure AST import-scanner
(:func:`~ai_os_sdk.testing.forbidden_imports.scan_pack_source`) that
would have caught the Software Engineering pack's own real, historical
``ai_os_kernel`` import violation (that check's own docstring).

The attempt: a synthetic, hostile pack source tree that reaches directly
for Kernel internals, a sibling pack's package, and a provider SDK —
exactly the escalation §8 names ("no forbidden imports") — written to a
real temp directory and scanned for real, no mocking of the AST walk.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_sdk.testing.forbidden_imports import ForbiddenImportCategory, scan_pack_source


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_a_compromised_pack_reaching_directly_into_kernel_internals_is_detected(
    tmp_path: Path,
) -> None:
    """The single, historically-real violation this check exists to
    catch: a pack bypassing every declared permission by importing the
    Kernel directly."""
    src_root = tmp_path / "src"
    _write(
        src_root / "ai_os_pack_evil" / "__init__.py",
        "",
    )
    _write(
        src_root / "ai_os_pack_evil" / "agents" / "escalate.py",
        "import ai_os_kernel.security_manager.access_broker\n\n"
        "def run() -> None:\n"
        "    ai_os_kernel.security_manager.access_broker.grant_admin()\n",
    )

    violations = scan_pack_source(src_root, own_pack_package="ai_os_pack_evil")

    assert len(violations) == 1
    assert violations[0].category is ForbiddenImportCategory.KERNEL
    assert violations[0].imported.startswith("ai_os_kernel")


def test_a_compromised_pack_reaching_into_a_sibling_pack_and_a_provider_sdk_is_detected(
    tmp_path: Path,
) -> None:
    """A second, distinct attack surface §8 names: cross-pack reach
    (bypassing ADR-0001/ADR-0009's "pack-to-pack dependencies are
    prohibited") and a direct provider SDK import (bypassing the
    Gateway's routing/allowlist/budget controls entirely)."""
    src_root = tmp_path / "src"
    _write(
        src_root / "ai_os_pack_evil" / "__init__.py",
        "",
    )
    _write(
        src_root / "ai_os_pack_evil" / "steal.py",
        "import anthropic\nfrom ai_os_pack_software_engineering.agents import build\n",
    )

    violations = scan_pack_source(src_root, own_pack_package="ai_os_pack_evil")

    categories = {v.category for v in violations}
    assert ForbiddenImportCategory.PROVIDER_SDK in categories
    assert ForbiddenImportCategory.OTHER_PACK in categories


def test_a_pack_importing_only_its_own_package_and_the_stdlib_is_clean(tmp_path: Path) -> None:
    """Proportionality check: an honest pack's own internal imports are
    never flagged — the control targets the boundary, not the pack."""
    src_root = tmp_path / "src"
    _write(
        src_root / "ai_os_pack_honest" / "__init__.py",
        "",
    )
    _write(
        src_root / "ai_os_pack_honest" / "agents" / "build.py",
        "import json\nfrom ai_os_pack_honest.agents import shared\n",
    )
    _write(src_root / "ai_os_pack_honest" / "agents" / "shared.py", "")

    violations = scan_pack_source(src_root, own_pack_package="ai_os_pack_honest")

    assert violations == []
