"""The documented, expiring waiver mechanism — real proof
(``platform_sdk_v1_scope.md`` step 8).

Covers the pure loading/matching/rendering logic with synthetic data
(no real filesystem I/O needed there), plus one real proof against the
actual, checked-in
``capability_packs/software-engineering/pack_contract_waiver.yaml`` —
the exact file CI reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_os_sdk.testing.forbidden_imports import ForbiddenImportCategory, ForbiddenImportViolation
from ai_os_sdk.testing.waiver import (
    ImportWaiver,
    WaiverFileError,
    apply_waiver,
    load_waiver,
    render_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_WAIVER_PATH = (
    _REPO_ROOT / "capability_packs" / "software-engineering" / "pack_contract_waiver.yaml"
)


def _violation(module: str, imported: str = "ai_os_kernel.something") -> ForbiddenImportViolation:
    return ForbiddenImportViolation(
        file=Path("some_file.py"),
        line=1,
        module=module,
        imported=imported,
        category=ForbiddenImportCategory.KERNEL,
    )


class TestLoadWaiver:
    def test_a_missing_file_yields_no_waiver(self, tmp_path: Path) -> None:
        assert load_waiver(tmp_path / "does_not_exist.yaml") is None

    def test_a_real_waiver_file_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "pack_contract_waiver.yaml"
        path.write_text(
            "check: 7\n"
            "plan_reference: docs/example.md\n"
            'granted: "2026-01-01"\n'
            "expires_at_step: 14\n"
            "reason: a test reason\n"
            "modules:\n"
            "  - some_pack.module_a\n"
            "  - some_pack.module_b\n",
            encoding="utf-8",
        )

        waiver = load_waiver(path)

        assert waiver is not None
        assert waiver.check == 7
        assert waiver.expires_at_step == 14
        assert waiver.modules == {"some_pack.module_a", "some_pack.module_b"}

    def test_a_non_mapping_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "pack_contract_waiver.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")

        with pytest.raises(WaiverFileError, match="mapping"):
            load_waiver(path)

    def test_a_missing_required_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "pack_contract_waiver.yaml"
        path.write_text("check: 7\nmodules: []\n", encoding="utf-8")

        with pytest.raises(WaiverFileError, match="missing required field"):
            load_waiver(path)

    def test_a_non_list_modules_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "pack_contract_waiver.yaml"
        path.write_text(
            "check: 7\n"
            "plan_reference: docs/example.md\n"
            'granted: "2026-01-01"\n'
            "expires_at_step: 14\n"
            "reason: a test reason\n"
            "modules: not_a_list\n",
            encoding="utf-8",
        )

        with pytest.raises(WaiverFileError, match="'modules' must be a list"):
            load_waiver(path)


class TestApplyWaiver:
    def test_no_waiver_means_everything_is_unwaived(self) -> None:
        violations = [_violation("pkg.a"), _violation("pkg.b")]

        application = apply_waiver(violations, None)

        assert application.unwaived == violations
        assert application.waived == []

    def test_only_listed_modules_are_waived(self) -> None:
        waiver = ImportWaiver(
            check=7,
            reason="test",
            plan_reference="docs/example.md",
            expires_at_step=14,
            granted="2026-01-01",
            modules=frozenset({"pkg.a"}),
        )
        covered = _violation("pkg.a")
        uncovered = _violation("pkg.b")

        application = apply_waiver([covered, uncovered], waiver)

        assert application.waived == [covered]
        assert application.unwaived == [uncovered]

    def test_a_new_violation_in_an_unlisted_module_still_fails(self) -> None:
        """The exact scenario the waiver's own docstring names: a waiver
        can never accidentally cover more than it explicitly lists."""

        waiver = ImportWaiver(
            check=7,
            reason="test",
            plan_reference="docs/example.md",
            expires_at_step=14,
            granted="2026-01-01",
            modules=frozenset({"pkg.a"}),
        )
        new_violation = _violation("pkg.brand_new_module")

        application = apply_waiver([new_violation], waiver)

        assert application.unwaived == [new_violation]


class TestRenderReport:
    def test_no_violations_at_all_is_a_clean_pass(self) -> None:
        application = apply_waiver([], None)
        assert render_report(application) == "[PASS] No unwaived forbidden imports."

    def test_unwaived_violations_are_visibly_a_failure(self) -> None:
        application = apply_waiver([_violation("pkg.a")], None)
        report = render_report(application)
        assert "[FAIL]" in report
        assert "pkg.a" not in report  # module name isn't printed, file:line is
        assert "some_file.py:1" in report

    def test_report_is_plain_ascii(self) -> None:
        """A real, discovered bug this guards against: emoji markers
        crashed with UnicodeEncodeError on Windows' default console
        codepage before this was fixed -- see waiver.py's own
        docstring."""
        application = apply_waiver([_violation("pkg.a")], None)
        render_report(application).encode("ascii")


class TestRealCheckedInWaiverFile:
    def test_the_real_waiver_file_loads_and_validates(self) -> None:
        waiver = load_waiver(_REAL_WAIVER_PATH)

        assert waiver is not None
        assert waiver.check == 7
        assert waiver.expires_at_step == 14
        assert "ai_os_pack_software_engineering.pack" in waiver.modules

    def test_the_real_waiver_report_is_plain_ascii(self) -> None:
        """Proves the actual, checked-in reason text -- not a synthetic
        stand-in -- also survives an ASCII-only console, the exact
        failure mode this step discovered and fixed."""
        waiver = load_waiver(_REAL_WAIVER_PATH)
        application = apply_waiver([_violation("ai_os_pack_software_engineering.pack")], waiver)
        render_report(application).encode("ascii")
