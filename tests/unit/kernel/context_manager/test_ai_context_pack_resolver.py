"""Unit tests for AIContextPackResolver — real file I/O against a real
tmp_path directory, following the real, documented format
(docs/ai_context/context_pack_structure.md §3/§4). The identical
precedent test_loader.py already uses for ConfigurationManager's own
not-yet-populated YAML files: never the actual repository
``ai_context/`` directory, which does not exist (see this module's own
docstring)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import AIContextPackError, AIContextPackResolver

_REQUEST = ContextRequest(workflow_id="wf_1", step_id="step_1")


def _write_manifest(pack_dir: Path, manifest: dict[str, Any]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")


def _write_content(pack_dir: Path, filename: str, content: str) -> None:
    (pack_dir / filename).write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_resolves_a_real_pack_with_real_content_files(tmp_path: Path) -> None:
    pack_dir = tmp_path / "platform" / "my-pack"
    _write_manifest(
        pack_dir, {"id": "my-pack", "name": "My Pack", "version": "1.0.0", "priority": 3}
    )
    _write_content(pack_dir, "00_invariants.md", "Never bypass the LLM Gateway.")
    _write_content(pack_dir, "01_architecture.md", "The Kernel has 20 documented components.")
    # 02_standards.md/03_current_state.md deliberately absent -- "not
    # every pack needs every file" (that document's own words).

    resolver = AIContextPackResolver(base_dir=tmp_path, pack_references=["platform/my-pack"])

    items = await resolver.resolve(_REQUEST)

    assert len(items) == 2
    by_identifier = {item.provenance.identifier: item for item in items}
    assert (
        by_identifier["ai_context_pack:my-pack@1.0.0:00_invariants.md"].content
        == "Never bypass the LLM Gateway."
    )
    assert (
        by_identifier["ai_context_pack:my-pack@1.0.0:01_architecture.md"].content
        == "The Kernel has 20 documented components."
    )
    for item in items:
        assert item.provenance.source_type == SourceType.AI_CONTEXT_PACK
        assert item.trust == "trusted"
        assert item.relevance_score == 3.0


@pytest.mark.asyncio
async def test_a_pack_with_no_declared_priority_gets_zero_relevance(tmp_path: Path) -> None:
    pack_dir = tmp_path / "platform" / "unscored-pack"
    _write_manifest(pack_dir, {"id": "unscored-pack", "version": "1.0.0"})
    _write_content(pack_dir, "00_invariants.md", "Some invariant text.")

    resolver = AIContextPackResolver(base_dir=tmp_path, pack_references=["platform/unscored-pack"])

    items = await resolver.resolve(_REQUEST)

    assert len(items) == 1
    assert items[0].relevance_score == 0.0


@pytest.mark.asyncio
async def test_a_missing_pack_directory_resolves_to_no_items_not_an_error(
    tmp_path: Path,
) -> None:
    resolver = AIContextPackResolver(base_dir=tmp_path, pack_references=["platform/does-not-exist"])

    items = await resolver.resolve(_REQUEST)

    assert items == []


@pytest.mark.asyncio
async def test_a_pack_directory_with_no_manifest_resolves_to_no_items(tmp_path: Path) -> None:
    pack_dir = tmp_path / "platform" / "undeclared-pack"
    pack_dir.mkdir(parents=True)
    _write_content(pack_dir, "00_invariants.md", "This pack was never declared.")

    resolver = AIContextPackResolver(
        base_dir=tmp_path, pack_references=["platform/undeclared-pack"]
    )

    items = await resolver.resolve(_REQUEST)

    assert items == []


@pytest.mark.asyncio
async def test_a_manifest_missing_version_is_rejected_as_malformed(tmp_path: Path) -> None:
    pack_dir = tmp_path / "platform" / "malformed-pack"
    _write_manifest(pack_dir, {"id": "malformed-pack"})
    _write_content(pack_dir, "00_invariants.md", "content")

    resolver = AIContextPackResolver(base_dir=tmp_path, pack_references=["platform/malformed-pack"])

    with pytest.raises(AIContextPackError, match="required"):
        await resolver.resolve(_REQUEST)


@pytest.mark.asyncio
async def test_multiple_pack_references_are_all_resolved(tmp_path: Path) -> None:
    pack_one = tmp_path / "platform" / "pack-one"
    _write_manifest(pack_one, {"id": "pack-one", "version": "1.0.0"})
    _write_content(pack_one, "00_invariants.md", "pack one content")

    pack_two = tmp_path / "kernel" / "pack-two"
    _write_manifest(pack_two, {"id": "pack-two", "version": "2.0.0"})
    _write_content(pack_two, "01_architecture.md", "pack two content")

    resolver = AIContextPackResolver(
        base_dir=tmp_path, pack_references=["platform/pack-one", "kernel/pack-two"]
    )

    items = await resolver.resolve(_REQUEST)

    assert {item.content for item in items} == {"pack one content", "pack two content"}


@pytest.mark.asyncio
async def test_ai_context_pack_content_flows_into_a_real_context_assembly(
    tmp_path: Path,
) -> None:
    pack_dir = tmp_path / "platform" / "assembly-pack"
    _write_manifest(pack_dir, {"id": "assembly-pack", "version": "1.0.0", "priority": 1})
    _write_content(pack_dir, "00_invariants.md", "Assembled invariant text.")

    resolver = AIContextPackResolver(base_dir=tmp_path, pack_references=["platform/assembly-pack"])
    context_manager = DefaultContextManager([resolver])

    assembled = await context_manager.assemble(_REQUEST)

    assert assembled.sources_queried == [SourceType.AI_CONTEXT_PACK]
    assert len(assembled.items) == 1
    assert assembled.items[0].content == "Assembled invariant text."
    assert assembled.items[0].provenance.source_type == SourceType.AI_CONTEXT_PACK
