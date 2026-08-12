"""Real proof that the Benchmarking pack's own manifest
(``P04-S03-M34-T05``) is discovered by the real Manifest Loader.

Closes Risk A of the 2026-08-11 health audit (risk register R-018) for
this pack: ``P04-S03-M34-T01``'s own body said "No manifest.yaml yet ...
(later ticket's scope)", that later ticket was never filed, and so this
pack was invisible to ``ManifestLoader.scan()`` entirely.

**Deliberately not a Postgres test, unlike the Project Intelligence
pack's own manifest test.** That pack declares five real Tools, so there
are genuine ``catalog.tools`` rows to assert on. This pack declares no
agent, tool or workflow, so a database-backed test would assert the
absence of rows nothing writes — a hollow proof. What is genuinely
provable here is that the manifest is schema-valid, that the real loader
finds it, and that its "no entryPoint" shape is the schema's own rule
rather than an omission — which the last test establishes by making the
schema reject the opposite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from ai_os_kernel.manifest_loader import ManifestError, ManifestLoader
from ai_os_kernel.manifest_loader.signature import SignatureStatus

REPO_ROOT = Path(__file__).resolve().parents[4]
PACK_ROOT = REPO_ROOT / "capability_packs" / "benchmarking"
SCHEMA_PATH = REPO_ROOT / "platform_sdk" / "schemas" / "manifest.schema.json"
PACK_ID = "benchmarking"


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((PACK_ROOT / "manifest.yaml").read_text("utf-8")))


def _loader(pack_dirs: list[str] | None = None) -> ManifestLoader:
    return ManifestLoader(
        pack_dirs=pack_dirs or [str(REPO_ROOT / "capability_packs")], schema_path=SCHEMA_PATH
    )


def test_the_real_loader_discovers_the_benchmarking_pack() -> None:
    """The ticket's own Output: a schema-valid manifest.yaml the real
    Manifest Loader loads. Asserted by id, never by count, so this test
    does not break the next time a pack is added."""
    report = _loader().scan()

    discovered = {m.metadata.id for m in report.discovered}
    assert PACK_ID in discovered, (
        "the Benchmarking pack is invisible to the real Manifest Loader — "
        "the exact gap this ticket exists to close"
    )
    assert report.failed == []


def test_load_one_accepts_the_committed_manifest_including_semantic_rules() -> None:
    """`load_one` fails closed, so this passing means schema validation
    *and* the semantic rules (notably rule 13's `sdkVersion` range check
    against the really-installed ai-os-sdk) both genuinely passed."""
    loaded = _loader().load_one(PACK_ROOT / "manifest.yaml")

    assert loaded.metadata.id == PACK_ID
    assert loaded.metadata.version == "0.1.0"


def test_the_pack_declares_nothing_invocable_and_says_so() -> None:
    """Guards the manifest's own central claim: this pack is
    discoverable, not invocable. If someone later adds an agent, tool or
    workflow here, this test fails and forces them to revisit the
    `entryPoint` rule and the empty permission set with it — rather than
    silently shipping a pack that declares capability nothing wired.
    """
    manifest = _manifest()

    assert "agents" not in manifest
    assert "tools" not in manifest
    assert "workflows" not in manifest
    # No entryPoint, because the schema requires one only alongside
    # agents/workflows — proven negatively by the final test below.
    assert "entryPoint" not in manifest
    # Deny-by-default: the pack does no I/O of any kind, so it asks for
    # nothing. An empty-but-present permissions list would be a
    # different, weaker statement than declaring none at all.
    assert "permissions" not in manifest


def test_no_pack_py_exists_because_none_is_required() -> None:
    """The corollary of the rule above, asserted against the filesystem:
    a stub `CapabilityPack` nothing would ever call is speculative code,
    so none was written."""
    assert not (PACK_ROOT / "src" / "ai_os_pack_benchmarking" / "pack.py").exists()


def test_the_manifest_is_unsigned_and_still_loads(tmp_path: Path) -> None:
    """FR-117 interaction, stated rather than assumed: verification is
    config-gated off by default, so this manifest loads and is honestly
    recorded as `unsigned`. No private key exists in this repository to
    sign it with."""
    loaded = _loader().load_one(PACK_ROOT / "manifest.yaml")

    assert loaded.signature.status is SignatureStatus.UNSIGNED
    assert not loaded.signature.is_trusted


def test_declaring_an_agent_without_an_entrypoint_is_genuinely_rejected(tmp_path: Path) -> None:
    """Proves the "no entryPoint" claim is the schema's rule, not an
    accident of this manifest.

    Take the real committed manifest, add an agent, change nothing else,
    and the schema's own `allOf` must reject it for the missing
    `entryPoint`. If this ever stops failing, the reasoning written into
    the manifest's header comment has become false.
    """
    manifest = _manifest()
    manifest["agents"] = [
        {
            "id": "benchmarking/example",
            "name": "Example Agent",
            "version": "0.1.0",
            "description": "Exists only to prove the schema's entryPoint rule is real.",
            "entryPoint": "ai_os_pack_benchmarking.example:ExampleAgent",
            "modelAlias": "default",
            "permissions": [],
        }
    ]
    pack_dir = tmp_path / "benchmarking"
    pack_dir.mkdir()
    (pack_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    with pytest.raises(ManifestError, match="entryPoint"):
        _loader([str(tmp_path)]).load_one(pack_dir / "manifest.yaml")
