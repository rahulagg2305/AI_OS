"""``pack_contract_suite`` — all 9 checks, run for real against the one
real, fully-migrated pack (``platform_sdk_v1_scope.md`` step 15).

**Why this lives here, not in ``platform_sdk/tests/``.** Every check
below imports and inspects the real, on-disk
``capability_packs/software-engineering`` pack — an inherently
cross-boundary assertion, the same reason
``tests/unit/platform_sdk/test_forbidden_imports_check.py`` and
``test_kernel_satisfies_sdk_contracts.py`` already live in the root
suite rather than the SDK's own dependency-floor suite.

**Why this directory, specifically.** ``.github/workflows/ci.yml``
already carries a prepared, gated ``contract`` job step —
``if: hashFiles('tests/contract/**') != ''`` / ``run: uv run pytest
tests/contract -v`` — inert since the directory did not exist. Real
tests landing here activate that CI gate with zero ``ci.yml`` changes,
mirroring exactly how step 8 activated
``scripts/check_import_boundaries.py``'s own gated step. ``tests/``
also has ``testpaths = ["tests"]`` (root ``pyproject.toml``), so these
tests are additionally part of the plain root ``pytest`` run, not only
the CI-gated one.

Each check gets its own real, individually-executed test — proving the
suite passes because each part of it does, not because one aggregate
assertion happened to be true. A separate test also runs the full
:func:`~ai_os_sdk.testing.run_pack_contract_suite` orchestrator, so the
end-to-end "all 9 together" path is exercised too, not only the
individual functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_sdk.testing import (
    PackContractSuiteReport,
    check_1_manifest_is_valid,
    check_2_entry_points_resolve,
    check_3_io_models_match,
    check_4_workflow_steps_resolve,
    check_5_trust_tier_consistency,
    check_6_permission_vocabulary,
    check_7_no_forbidden_imports,
    check_8_required_prompts_exist,
    check_9_clean_activation,
    render_suite_report,
    run_pack_contract_suite,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SE_PACK_ROOT = _REPO_ROOT / "capability_packs" / "software-engineering"
_SE_MANIFEST_PATH = _SE_PACK_ROOT / "manifest.yaml"
_SCHEMA_PATH = _REPO_ROOT / "platform_sdk" / "schemas" / "manifest.schema.json"
_SE_PACK_PACKAGE = "ai_os_pack_software_engineering"
_SE_WAIVER_PATH = _SE_PACK_ROOT / "pack_contract_waiver.yaml"


@pytest.fixture
def manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(_SE_MANIFEST_PATH.read_text(encoding="utf-8"))
    return loaded


class TestCheck1ManifestIsValid:
    def test_the_real_manifest_is_schema_valid(self) -> None:
        result = check_1_manifest_is_valid(_SE_MANIFEST_PATH, _SCHEMA_PATH)
        assert result.passed, result.details

    def test_a_manifest_missing_a_required_field_fails(self, tmp_path: Path) -> None:
        broken = tmp_path / "manifest.yaml"
        broken.write_text("apiVersion: ai-os/v1\nkind: CapabilityPack\n", encoding="utf-8")
        result = check_1_manifest_is_valid(broken, _SCHEMA_PATH)
        assert not result.passed

    def test_declared_sdk_version_range_is_satisfied_by_the_real_installed_sdk(self) -> None:
        """The real manifest declares dependencies.sdkVersion:
        '>=0.1.0,<1.0.0' — genuinely checked against the real, installed
        ai-os-sdk distribution version, not merely schema-shape-checked."""
        result = check_1_manifest_is_valid(_SE_MANIFEST_PATH, _SCHEMA_PATH)
        assert any("sdkVersion" in d and "satisfied" in d for d in result.details)


class TestCheck2EntryPointsResolve:
    def test_every_real_entry_point_resolves(self, manifest: dict[str, Any]) -> None:
        result = check_2_entry_points_resolve(manifest, _SE_PACK_ROOT)
        assert result.passed, result.details

    def test_a_nonexistent_entrypoint_fails(self, manifest: dict[str, Any]) -> None:
        broken = dict(manifest)
        broken["entryPoint"] = "ai_os_pack_software_engineering.pack:DoesNotExist"
        result = check_2_entry_points_resolve(broken, _SE_PACK_ROOT)
        assert not result.passed

    def test_a_missing_workflow_definition_file_fails(self, manifest: dict[str, Any]) -> None:
        broken_workflow = {
            **manifest["workflows"][0],
            "definition": "workflows/does_not_exist.yaml",
        }
        broken = {**manifest, "workflows": [broken_workflow]}
        result = check_2_entry_points_resolve(broken, _SE_PACK_ROOT)
        assert not result.passed


class TestCheck3IoModelsMatch:
    def test_every_real_agent_and_workflow_io_model_matches(self, manifest: dict[str, Any]) -> None:
        result = check_3_io_models_match(manifest)
        assert result.passed, result.details

    def test_an_unresolvable_output_schema_fails(self, manifest: dict[str, Any]) -> None:
        broken_agent = dict(manifest["agents"][1])  # architecture
        broken_agent["outputSchema"] = (
            "ai_os_pack_software_engineering.agents.architecture:NoSuchModel"
        )
        broken = {**manifest, "agents": [broken_agent]}
        result = check_3_io_models_match(broken)
        assert not result.passed


class TestCheck4WorkflowStepsResolve:
    def test_every_real_workflow_step_resolves(self, manifest: dict[str, Any]) -> None:
        result = check_4_workflow_steps_resolve(manifest, _SE_PACK_ROOT)
        assert result.passed, result.details

    def test_a_step_naming_an_undeclared_agent_id_fails(
        self, manifest: dict[str, Any], tmp_path: Path
    ) -> None:
        bad_definition = tmp_path / "bad_workflow.yaml"
        bad_definition.write_text(
            "steps:\n  - id: bogus\n    agentId: software-engineering/does-not-exist\n",
            encoding="utf-8",
        )
        broken_workflow = dict(manifest["workflows"][0])
        # An absolute path here deliberately bypasses pack_root joining
        # (Path("root") / Path("/abs/path") yields "/abs/path" unchanged)
        # -- simplest way to point check_4 at a real file outside the
        # pack tree without writing into the pack's own directory.
        broken_workflow["definition"] = str(bad_definition)
        broken = {**manifest, "workflows": [broken_workflow]}
        result = check_4_workflow_steps_resolve(broken, _SE_PACK_ROOT)
        assert not result.passed


class TestCheck5TrustTierConsistency:
    def test_the_real_platform_sandbox_tool_is_tier1_sandboxed(
        self, manifest: dict[str, Any]
    ) -> None:
        result = check_5_trust_tier_consistency(manifest)
        assert result.passed, result.details
        assert any("TIER1_SANDBOXED" in d for d in result.details)


class TestCheck6PermissionVocabulary:
    def test_every_real_permission_is_in_the_closed_vocabulary(
        self, manifest: dict[str, Any]
    ) -> None:
        result = check_6_permission_vocabulary(manifest, _SCHEMA_PATH)
        assert result.passed, result.details

    def test_an_unknown_per_agent_permission_fails(self, manifest: dict[str, Any]) -> None:
        """The real, confirmed gap this check closes: the schema does
        not enum-constrain per-agent permissions, so this is the only
        mechanism that would ever catch this."""
        broken_agent = dict(manifest["agents"][0])
        broken_agent["permissions"] = ["not:a:real:permission"]
        broken = {**manifest, "agents": [broken_agent]}
        result = check_6_permission_vocabulary(broken, _SCHEMA_PATH)
        assert not result.passed


class TestCheck7NoForbiddenImports:
    def test_the_real_pack_has_zero_forbidden_imports_with_no_waiver(self) -> None:
        assert not _SE_WAIVER_PATH.exists()
        result = check_7_no_forbidden_imports(
            _SE_PACK_ROOT, own_pack_package=_SE_PACK_PACKAGE, waiver_path=_SE_WAIVER_PATH
        )
        assert result.passed, result.details


class TestCheck8RequiredPromptsExist:
    def test_every_required_prompt_resolves_to_a_real_nonempty_file(
        self, manifest: dict[str, Any]
    ) -> None:
        result = check_8_required_prompts_exist(manifest, _SE_PACK_ROOT)
        assert result.passed, result.details

    def test_a_required_prompt_with_no_matching_declaration_fails(
        self, manifest: dict[str, Any]
    ) -> None:
        broken_agent = dict(manifest["agents"][1])  # architecture
        broken_agent["requiredPrompts"] = ["no.such.prompt@9.9.9"]
        broken = {**manifest, "agents": [broken_agent]}
        result = check_8_required_prompts_exist(broken, _SE_PACK_ROOT)
        assert not result.passed


class TestCheck9CleanActivation:
    async def test_the_real_pack_activates_reports_health_and_deactivates_cleanly(
        self, manifest: dict[str, Any]
    ) -> None:
        result = await check_9_clean_activation(manifest)
        assert result.passed, result.details
        assert any("architecture" in d for d in result.details)

    async def test_a_nonexistent_entry_point_fails_rather_than_raising(
        self, manifest: dict[str, Any]
    ) -> None:
        broken = {**manifest, "entryPoint": "ai_os_pack_software_engineering.pack:DoesNotExist"}
        result = await check_9_clean_activation(broken)
        assert not result.passed


class TestFullSuiteAgainstTheRealPack:
    """The end-to-end proof the closeout report cites: all 9 checks,
    run together through the one real orchestrator, against the one
    real, fully-migrated pack — genuinely green, not asserted."""

    async def test_all_nine_checks_pass_together(self) -> None:
        report = await run_pack_contract_suite(
            pack_root=_SE_PACK_ROOT,
            manifest_path=_SE_MANIFEST_PATH,
            schema_path=_SCHEMA_PATH,
            own_pack_package=_SE_PACK_PACKAGE,
            waiver_path=_SE_WAIVER_PATH,
        )
        rendered = render_suite_report(report)
        assert report.passed, rendered
        assert len(report.results) == 9
        assert [r.check_id for r in report.results] == list(range(1, 10))

    async def test_report_renders_without_error_and_is_plain_ascii(self) -> None:
        report = await run_pack_contract_suite(
            pack_root=_SE_PACK_ROOT,
            manifest_path=_SE_MANIFEST_PATH,
            schema_path=_SCHEMA_PATH,
            own_pack_package=_SE_PACK_PACKAGE,
            waiver_path=_SE_WAIVER_PATH,
        )
        rendered = render_suite_report(report)
        rendered.encode("ascii")  # UnicodeEncodeError if not -- waiver.render_report's precedent
        assert isinstance(report, PackContractSuiteReport)


class TestOrchestratorSurvivesAnUnreadableManifest:
    """A real, fixed regression: `run_pack_contract_suite()` used to call
    the unguarded manifest loader directly and would crash with an
    uncaught exception if the manifest were invalid YAML or a
    non-mapping document -- losing every check's own result, not just
    check 1's. Fixed to run check 1 first and report a clean,
    all-9-checks-present failure instead."""

    async def test_an_unreadable_manifest_produces_a_clean_failed_report_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        bad_manifest = tmp_path / "manifest.yaml"
        bad_manifest.write_text("key: [unterminated\n", encoding="utf-8")

        report = await run_pack_contract_suite(
            pack_root=_SE_PACK_ROOT,
            manifest_path=bad_manifest,
            schema_path=_SCHEMA_PATH,
            own_pack_package=_SE_PACK_PACKAGE,
            waiver_path=_SE_WAIVER_PATH,
        )

        assert not report.passed
        assert len(report.results) == 9
        assert [r.check_id for r in report.results] == list(range(1, 10))
        assert not report.results[0].passed  # check 1 itself fails, cleanly
        # check 7 is manifest-independent and still runs for real against the real pack
        assert report.results[6].check_id == 7
        assert report.results[6].passed
