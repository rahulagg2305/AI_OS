"""Real, deterministic tests for the `architecture.recover` Tool —
pure computation over already-known graph data, no sandbox/fake needed
at all (ADR-0004/ADR-0015 don't even apply: there is no I/O or
non-determinism here worth substituting)."""

from __future__ import annotations

import pytest

from ai_os_pack_project_intelligence.tools.architecture_recovery import (
    ArchitectureRecoveryOutput,
    ArchitectureRecoveryToolEntrypoint,
    ArchitectureRecoveryToolInputError,
)


def _node(path: str) -> dict[str, str]:
    return {"path": path}


def _edge(from_path: str, to_path: str) -> dict[str, str]:
    return {"from": from_path, "to": to_path, "importedName": "x"}


def test_entrypoint_is_tier2_trusted_not_tier1_sandboxed() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()

    assert tool.trust_tier.value == "tier2_trusted"


@pytest.mark.asyncio
async def test_missing_nodes_or_edges_raises_a_clear_error() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()

    with pytest.raises(ArchitectureRecoveryToolInputError, match="requires 'nodes'"):
        await tool.execute({"edges": []})


@pytest.mark.asyncio
async def test_a_malformed_node_raises_a_clear_error() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()

    with pytest.raises(ArchitectureRecoveryToolInputError, match="requires every 'nodes' entry"):
        await tool.execute({"nodes": [{"nope": 1}], "edges": []})


@pytest.mark.asyncio
async def test_a_malformed_edge_raises_a_clear_error() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()

    with pytest.raises(ArchitectureRecoveryToolInputError, match="requires every 'edges' entry"):
        await tool.execute({"nodes": [], "edges": [{"from": "a"}]})


@pytest.mark.asyncio
async def test_intra_module_edges_produce_no_module_edge() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("pkg/a.py"), _node("pkg/b.py")]
    edges = [_edge("pkg/a.py", "pkg/b.py")]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    ArchitectureRecoveryOutput.model_validate(outputs)
    assert outputs["moduleEdges"] == []
    assert outputs["circularDependencies"] == []
    modules = {m["name"]: m for m in outputs["modules"]}
    assert modules["pkg"]["fanIn"] == 0
    assert modules["pkg"]["fanOut"] == 0


@pytest.mark.asyncio
async def test_a_real_inter_module_edge_is_aggregated_with_a_count() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("api/a.py"), _node("api/b.py"), _node("core/x.py")]
    edges = [_edge("api/a.py", "core/x.py"), _edge("api/b.py", "core/x.py")]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    assert outputs["moduleEdges"] == [{"from": "api", "to": "core", "fileEdgeCount": 2}]
    modules = {m["name"]: m for m in outputs["modules"]}
    assert modules["api"]["fanOut"] == 1
    assert modules["api"]["fanIn"] == 0
    assert modules["core"]["fanIn"] == 1
    assert modules["core"]["fanOut"] == 0


@pytest.mark.asyncio
async def test_root_level_files_are_grouped_into_the_dot_module() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("main.py"), _node("pkg/a.py")]
    edges = [_edge("main.py", "pkg/a.py")]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    names = {m["name"] for m in outputs["modules"]}
    assert names == {".", "pkg"}
    assert outputs["moduleEdges"] == [{"from": ".", "to": "pkg", "fileEdgeCount": 1}]


@pytest.mark.asyncio
async def test_a_real_two_module_cycle_is_detected() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("a/x.py"), _node("b/y.py")]
    edges = [_edge("a/x.py", "b/y.py"), _edge("b/y.py", "a/x.py")]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    assert outputs["circularDependencies"] == [{"cycle": ["a", "b", "a"]}]


@pytest.mark.asyncio
async def test_a_real_three_module_cycle_is_detected() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("a/x.py"), _node("b/y.py"), _node("c/z.py")]
    edges = [
        _edge("a/x.py", "b/y.py"),
        _edge("b/y.py", "c/z.py"),
        _edge("c/z.py", "a/x.py"),
    ]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    assert outputs["circularDependencies"] == [{"cycle": ["a", "b", "c", "a"]}]


@pytest.mark.asyncio
async def test_a_linear_chain_has_no_circular_dependency() -> None:
    tool = ArchitectureRecoveryToolEntrypoint()
    nodes = [_node("a/x.py"), _node("b/y.py"), _node("c/z.py")]
    edges = [_edge("a/x.py", "b/y.py"), _edge("b/y.py", "c/z.py")]

    outputs = await tool.execute({"nodes": nodes, "edges": edges})

    assert outputs["circularDependencies"] == []


@pytest.mark.asyncio
async def test_every_real_output_is_genuinely_tagged_untrusted() -> None:
    """FR-059's own invariant, reused here since this Tool also derives
    entirely from ingested-repository-sourced content."""
    tool = ArchitectureRecoveryToolEntrypoint()

    outputs = await tool.execute({"nodes": [], "edges": []})

    assert outputs["trust"] == "untrusted"


def test_input_and_output_models_document_the_tool_contract() -> None:
    ArchitectureRecoveryOutput(
        modules=[{"name": "pkg", "fanIn": 0, "fanOut": 1}],
        module_edges=[{"from": "pkg", "to": "core", "fileEdgeCount": 1}],
        circular_dependencies=[],
        trust="untrusted",
    )
