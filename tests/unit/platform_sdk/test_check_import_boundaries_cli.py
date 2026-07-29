"""Real, end-to-end proof of ``scripts/check_import_boundaries.py`` —
the exact CI entry point (``platform_sdk_v1_scope.md`` step 8).

**Two real scenarios, both genuinely executed, neither mocked:**

1. Against the real, checked-in Software Engineering pack, with its
   real, checked-in waiver in place — the exact state CI runs against
   today. Proves ``main()`` returns 0.
2. Against a synthetic pack, constructed fresh under ``tmp_path`` with a
   real ``ai_os_kernel`` import and deliberately **no** waiver file —
   proving the check genuinely fails when nothing waives a real
   violation. This does not touch the real repository's own waiver file
   at any point (unlike temporarily deleting and restoring it by hand,
   which is what this step's own manual proof did once, live, before
   this automated version replaced it as the durable regression check).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.check_import_boundaries as cli


class TestRealRepoWithRealWaiver:
    def test_main_passes_against_the_real_pack_and_its_real_waiver(self) -> None:
        assert cli.main() == 0


def _build_fake_pack(packs_root: Path) -> None:
    pack_root = packs_root / "example-pack"
    src = pack_root / "src" / "ai_os_pack_example"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "agent.py").write_text("import ai_os_kernel.workflow_engine.agent\n", encoding="utf-8")
    (pack_root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "ai-os-pack-example"\n'
        "\n"
        "[tool.hatch.build.targets.wheel]\n"
        'packages = ["src/ai_os_pack_example"]\n',
        encoding="utf-8",
    )


class TestSyntheticPackWithNoWaiver:
    def test_main_fails_with_no_waiver_file_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packs_root = tmp_path / "capability_packs"
        packs_root.mkdir()
        _build_fake_pack(packs_root)

        monkeypatch.setattr(cli, "_PACKS_ROOT", packs_root)

        assert cli.main() == 1

    def test_main_passes_once_a_matching_waiver_is_added(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The direct before/after proof: identical synthetic
        violation, only the waiver file's presence differs."""
        packs_root = tmp_path / "capability_packs"
        packs_root.mkdir()
        _build_fake_pack(packs_root)
        (packs_root / "example-pack" / "pack_contract_waiver.yaml").write_text(
            "check: 7\n"
            "plan_reference: docs/example.md\n"
            'granted: "2026-01-01"\n'
            "expires_at_step: 99\n"
            "reason: synthetic test waiver\n"
            "modules:\n"
            "  - ai_os_pack_example.agent\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(cli, "_PACKS_ROOT", packs_root)

        assert cli.main() == 0
