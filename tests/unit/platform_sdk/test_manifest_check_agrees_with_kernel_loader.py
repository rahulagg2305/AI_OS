"""Confirms `ai_os_sdk.testing.pack_contract_suite.check_1_manifest_is_valid`
(step 15) and the real, production `ai_os_kernel.manifest_loader.ManifestLoader`
(the pre-existing, separate mechanism check 1's own docstring says it
duplicates rather than imports, since the SDK's dependency-floor rule
forbids importing `ai_os_kernel`) genuinely agree on accept/reject for
the same real manifest documents — not assumed from reading both
implementations side by side.

**Why this lives here, not in `platform_sdk/tests/`.** This test
imports both `ai_os_kernel` and `ai_os_sdk` together — an inherently
cross-boundary assertion, the same reason `test_kernel_satisfies_sdk_contracts.py`
already lives in this directory rather than the SDK's own
dependency-floor suite.

**What was actually found comparing the two implementations line by
line** (recorded here, not silently absorbed): `ManifestLoader._build_validator`
additionally calls `Draft202012Validator.check_schema(schema)` — a
self-check that the *schema file itself* is well-formed, irrelevant to
whether a given *manifest* is accepted, since it never varies per
manifest. `ManifestLoader.load_one` also parses `metadata` into a
`PackMetadata` pydantic model (`id`/`name`/`version`/`description`/`owner`,
all plain `str`) after schema validation passes — `check_1_manifest_is_valid`
does not. This is a real, structural difference in *what code path
runs*, but not one that can produce a *different accept/reject verdict*:
every one of `PackMetadata`'s fields is already required and
type-constrained to `string` by the schema itself
(`manifest.schema.json`'s own `metadata.required`), so any manifest that
already passes schema validation is guaranteed to also satisfy
`PackMetadata.model_validate()` — there is no manifest shape that could
reach `_extract_metadata` and still fail it. The tests below prove this
empirically across the real pack manifest and several synthetically
broken variants, rather than resting on that argument alone.

**One real, genuine, one-directional divergence found and confirmed —
not a bug, but real enough to need its own explicit test
(`TestTheOneRealKnownDivergence` below) rather than being silently
absorbed into the "they agree" claim.** `check_1_manifest_is_valid`
additionally checks the manifest's declared `dependencies.sdkVersion`
range against the real, installed `ai-os-sdk` distribution version
(`platform_sdk_v1_scope.md` step 15's own stated scope) — `ManifestLoader`
has no such concept and never performs this check at all. The SDK-side
check is therefore *strictly stricter* on this one field: every manifest
`ManifestLoader` rejects, `check_1_manifest_is_valid` also rejects (the
9 cases above prove this), but a manifest declaring an `sdkVersion`
range the installed SDK cannot satisfy is accepted by `ManifestLoader`
and rejected by `check_1_manifest_is_valid`. This is intentional — check
1 is scoped to also cover "dependencies are satisfied," which
`ManifestLoader` was never built to check — and one-directional only:
there is no manifest shape `check_1_manifest_is_valid` accepts and
`ManifestLoader` rejects.

**A second, real defect found and fixed while writing this test, not
merely a divergence to document**: `check_1_manifest_is_valid` used to
raise an uncaught `ValueError`/`yaml.YAMLError` for a non-mapping or
invalid-YAML document instead of returning `passed=False` — the one
behavior every other check in this suite avoids. Fixed in
`pack_contract_suite.py` (`_ManifestUnreadable`); `run_pack_contract_suite()`
itself was also fixed, since it called the same unguarded loader
directly and would have crashed the entire 9-check run over one
unreadable manifest, not merely failed check 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_os_kernel.manifest_loader import ManifestError, ManifestLoader
from ai_os_sdk.testing import check_1_manifest_is_valid

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_PATH = _REPO_ROOT / "platform_sdk" / "schemas" / "manifest.schema.json"
_SE_MANIFEST_PATH = _REPO_ROOT / "capability_packs" / "software-engineering" / "manifest.yaml"

_MINIMAL_VALID_MANIFEST: dict[str, Any] = {
    "apiVersion": "ai-os/v1",
    "kind": "CapabilityPack",
    "metadata": {
        "id": "example-pack",
        "name": "Example Pack",
        "version": "0.1.0",
        "description": "A fixture pack used only by this parity test.",
        "owner": "test-owner",
        "license": "UNLICENSED",
    },
    "compatibility": {"minKernelVersion": "0.1.0"},
    "dependencies": {"sdkVersion": ">=0.1.0,<1.0.0"},
}


def _kernel_accepts(manifest_path: Path) -> bool:
    loader = ManifestLoader(pack_dirs=[], schema_path=_SCHEMA_PATH)
    try:
        loader.load_one(manifest_path)
    except ManifestError:
        return False
    return True


def _sdk_accepts(manifest_path: Path) -> bool:
    return check_1_manifest_is_valid(manifest_path, _SCHEMA_PATH).passed


def _assert_both_agree(manifest_path: Path, *, expected: bool) -> None:
    kernel_result = _kernel_accepts(manifest_path)
    sdk_result = _sdk_accepts(manifest_path)
    assert kernel_result == expected, (
        f"ManifestLoader accepted={kernel_result}, expected={expected}"
    )
    assert sdk_result == expected, (
        f"check_1_manifest_is_valid accepted={sdk_result}, expected={expected}"
    )
    assert kernel_result == sdk_result, (
        f"DISAGREEMENT: ManifestLoader accepted={kernel_result}, "
        f"check_1_manifest_is_valid accepted={sdk_result}, for {manifest_path}"
    )


def _write(tmp_path: Path, name: str, content: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


class TestAgreementOnTheRealPackManifest:
    def test_both_accept_the_real_software_engineering_manifest(self) -> None:
        _assert_both_agree(_SE_MANIFEST_PATH, expected=True)


class TestAgreementOnSyntheticVariants:
    """Each variant is a real, on-disk manifest file both implementations
    load fresh — not a mocked or in-memory shortcut."""

    def test_both_accept_a_minimal_valid_manifest(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "manifest.yaml", _MINIMAL_VALID_MANIFEST)
        _assert_both_agree(path, expected=True)

    def test_both_reject_a_manifest_missing_a_required_top_level_field(
        self, tmp_path: Path
    ) -> None:
        broken = {k: v for k, v in _MINIMAL_VALID_MANIFEST.items() if k != "compatibility"}
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_a_manifest_missing_a_required_metadata_field(self, tmp_path: Path) -> None:
        metadata_without_owner = {
            k: v for k, v in _MINIMAL_VALID_MANIFEST["metadata"].items() if k != "owner"
        }
        broken = {**_MINIMAL_VALID_MANIFEST, "metadata": metadata_without_owner}
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_an_unknown_top_level_permission(self, tmp_path: Path) -> None:
        broken = {**_MINIMAL_VALID_MANIFEST, "permissions": ["not:a:real:permission"]}
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_an_invalid_metadata_version_format(self, tmp_path: Path) -> None:
        broken = {
            **_MINIMAL_VALID_MANIFEST,
            "metadata": {**_MINIMAL_VALID_MANIFEST["metadata"], "version": "not-a-semver"},
        }
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_an_unknown_top_level_property(self, tmp_path: Path) -> None:
        broken = {**_MINIMAL_VALID_MANIFEST, "thisFieldDoesNotExist": True}
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_agents_present_without_an_entry_point(self, tmp_path: Path) -> None:
        """Exercises the schema's own cross-field `allOf` rule (entryPoint
        required once agents[] is non-empty) through both code paths."""
        broken = {
            **_MINIMAL_VALID_MANIFEST,
            "agents": [
                {
                    "id": "example-agent",
                    "name": "Example Agent",
                    "version": "0.1.0",
                    "purpose": "A fixture agent for this parity test only.",
                    "entrypoint": "some.module:SomeClass",
                    "inputSchema": "some.module:SomeInput",
                    "outputSchema": "some.module:SomeOutput",
                }
            ],
            # entryPoint deliberately omitted
        }
        path = _write(tmp_path, "manifest.yaml", broken)
        _assert_both_agree(path, expected=False)

    def test_both_reject_a_non_mapping_document(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        _assert_both_agree(path, expected=False)

    def test_both_reject_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.yaml"
        path.write_text("key: [unterminated\n", encoding="utf-8")
        _assert_both_agree(path, expected=False)


class TestTheOneRealKnownDivergence:
    """`check_1_manifest_is_valid` additionally checks
    `dependencies.sdkVersion` against the real, installed `ai-os-sdk`
    version (`platform_sdk_v1_scope.md` step 15's own stated scope,
    "dependencies are satisfied") — `ManifestLoader` does not check this
    at all; it has no concept of an installed SDK version to compare
    against. This is a real, intentional, one-directional divergence:
    the SDK-side check is *strictly stricter* on this one field, never
    laxer. Documented here explicitly, with a real failing case, rather
    than left to be discovered as a surprise."""

    def test_the_sdk_check_rejects_an_sdk_version_range_the_installed_sdk_does_not_satisfy(
        self, tmp_path: Path
    ) -> None:
        manifest = {
            **_MINIMAL_VALID_MANIFEST,
            "dependencies": {"sdkVersion": ">=99.0.0,<100.0.0"},
        }
        path = _write(tmp_path, "manifest.yaml", manifest)

        kernel_result = _kernel_accepts(path)
        sdk_result = _sdk_accepts(path)

        assert kernel_result is True, (
            "ManifestLoader has no sdkVersion-satisfaction concept and should still accept "
            "this manifest on schema grounds alone"
        )
        assert sdk_result is False, (
            "check_1_manifest_is_valid should reject this manifest: the installed ai-os-sdk "
            "version cannot satisfy '>=99.0.0,<100.0.0'"
        )
