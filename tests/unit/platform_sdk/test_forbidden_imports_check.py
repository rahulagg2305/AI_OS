"""``pack_contract_suite`` check 7 — real proof, not assumption
(``platform_sdk_v1_scope.md`` step 8).

Two kinds of proof: synthetic-source unit tests for each of the five
forbidden categories (so every category is exercised even though the
one real pack today only ever triggers one of them), and a real scan of
the actual, on-disk Software Engineering pack source tree, confirming
the exact violation count and module set this step's own report cites
— not a number copied from a prior manual run.

**Why this lives in the root suite, not ``platform_sdk/tests/``.** The
real-pack proof imports a real pack's source tree — an inherently
cross-boundary assertion, the same reason
``test_kernel_satisfies_sdk_contracts.py`` and
``test_context_service_and_capability_pack.py`` live here rather than
in the SDK's own dependency-floor suite.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_sdk.testing.forbidden_imports import (
    ForbiddenImportCategory,
    scan_module_source,
    scan_pack_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SE_PACK_SRC = _REPO_ROOT / "capability_packs" / "software-engineering" / "src"
_SE_PACK_PACKAGE = "ai_os_pack_software_engineering"


class TestEachForbiddenCategoryIsDetected:
    """Synthetic sources, one per category — the one real pack today
    only ever triggers KERNEL, so the other four need a constructed
    example to prove the scanner recognizes them at all."""

    def _scan(self, source: str) -> list[ForbiddenImportCategory]:
        violations = scan_module_source(
            source,
            Path("synthetic.py"),
            own_pack_package="ai_os_pack_example",
            module="ai_os_pack_example.synthetic",
        )
        return [v.category for v in violations]

    def test_ai_os_kernel_import_statement(self) -> None:
        assert self._scan("import ai_os_kernel.workflow_engine.agent\n") == [
            ForbiddenImportCategory.KERNEL
        ]

    def test_ai_os_kernel_from_import(self) -> None:
        assert self._scan("from ai_os_kernel.workflow_engine.agent import Agent\n") == [
            ForbiddenImportCategory.KERNEL
        ]

    def test_ai_os_services_import(self) -> None:
        assert self._scan("import ai_os_services.notifications\n") == [
            ForbiddenImportCategory.PLATFORM_SERVICE
        ]

    def test_another_packs_import(self) -> None:
        assert self._scan("from ai_os_pack_other_thing.agents import build\n") == [
            ForbiddenImportCategory.OTHER_PACK
        ]

    def test_own_packs_import_is_not_a_violation(self) -> None:
        """The exact case that must NOT fire -- a pack importing its own
        sibling modules is normal, expected structure."""
        assert self._scan("from ai_os_pack_example.agents import build\n") == []

    def test_provider_sdk_import(self) -> None:
        assert self._scan("import anthropic\n") == [ForbiddenImportCategory.PROVIDER_SDK]

    def test_database_driver_import(self) -> None:
        assert self._scan("from sqlalchemy.ext.asyncio import AsyncEngine\n") == [
            ForbiddenImportCategory.DATABASE_DRIVER
        ]

    def test_direct_http_client_import(self) -> None:
        assert self._scan("import httpx\n") == [ForbiddenImportCategory.HTTP_CLIENT]

    def test_an_unrelated_import_is_not_a_violation(self) -> None:
        assert self._scan("import pydantic\nfrom pathlib import Path\n") == []

    def test_line_numbers_are_real_not_fabricated(self) -> None:
        violations = scan_module_source(
            "from pathlib import Path\n\nimport ai_os_kernel.bootstrap\n",
            Path("synthetic.py"),
            own_pack_package="ai_os_pack_example",
            module="ai_os_pack_example.synthetic",
        )
        assert len(violations) == 1
        assert violations[0].line == 3


class TestRealSoftwareEngineeringPackScan:
    """The exact, current, real state of the one real pack's own source
    tree — re-scanned fresh, not assumed from a prior run.

    **Step 14 migrated the last remaining module (`pack.py`) — this
    pack now has zero `ai_os_kernel` imports anywhere, the first time
    that has been true in this project's history.** `pack_contract_waiver.yaml`
    is deleted outright (not merely emptied); see `pack.py`'s own
    docstring and `platform_sdk_v1_scope.md` §6r for the full record.
    """

    def test_the_pack_has_zero_forbidden_imports_at_all(self) -> None:
        """Guards this pack's own fully-migrated state against silent
        drift -- if any module ever starts importing ai_os_kernel (or
        any other forbidden category) again, this test fails
        immediately, with no waiver anywhere in this pack to catch it."""
        violations = scan_pack_source(_SE_PACK_SRC, own_pack_package=_SE_PACK_PACKAGE)
        assert violations == []

    def test_every_agent_and_the_pack_entry_point_are_migrated(self) -> None:
        """Steps 9-14's own real proof, at the scanner level: every
        module this pack ships -- all five agents and the CapabilityPack
        entry point itself -- imports nothing ai_os_kernel at all."""
        violations = scan_pack_source(_SE_PACK_SRC, own_pack_package=_SE_PACK_PACKAGE)
        fully_migrated_modules = {
            f"{_SE_PACK_PACKAGE}.agents.verification",
            f"{_SE_PACK_PACKAGE}.agents.requirements_analyst",
            f"{_SE_PACK_PACKAGE}.agents.architecture",
            f"{_SE_PACK_PACKAGE}.agents.build",
            f"{_SE_PACK_PACKAGE}.agents.documentation",
            f"{_SE_PACK_PACKAGE}.pack",
        }
        assert not any(v.module in fully_migrated_modules for v in violations)

    def test_pipeline_py_is_gone_so_it_contributes_no_violations(self) -> None:
        """Step 7 relocated pipeline.py out of this tree entirely -- if
        it ever reappeared here, its own sqlalchemy import would show up
        as a DATABASE_DRIVER violation this test would catch."""
        violations = scan_pack_source(_SE_PACK_SRC, own_pack_package=_SE_PACK_PACKAGE)
        assert not any("pipeline" in v.module for v in violations)
