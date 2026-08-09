"""Real, deterministic tests for the `documentation.generate` Tool —
pure rendering over already-known facts, no sandbox/fake needed at all
(ADR-0004/ADR-0015 don't even apply: there is no I/O or
non-determinism here worth substituting)."""

from __future__ import annotations

import pytest

from ai_os_pack_project_intelligence.tools.documentation_generation import (
    DocumentationGenerationOutput,
    DocumentationGenerationToolEntrypoint,
    DocumentationGenerationToolInputError,
)


def _module(name: str, fan_in: int, fan_out: int) -> dict[str, object]:
    return {"name": name, "fanIn": fan_in, "fanOut": fan_out}


def test_entrypoint_is_tier2_trusted_not_tier1_sandboxed() -> None:
    tool = DocumentationGenerationToolEntrypoint()

    assert tool.trust_tier.value == "tier2_trusted"


@pytest.mark.asyncio
async def test_missing_fields_raise_a_clear_error() -> None:
    tool = DocumentationGenerationToolEntrypoint()

    with pytest.raises(DocumentationGenerationToolInputError, match="requires 'modules'"):
        await tool.execute({"moduleEdges": [], "circularDependencies": []})


@pytest.mark.asyncio
async def test_a_malformed_module_raises_a_clear_error() -> None:
    tool = DocumentationGenerationToolEntrypoint()

    with pytest.raises(DocumentationGenerationToolInputError, match="requires every 'modules'"):
        await tool.execute(
            {"modules": [{"name": "pkg"}], "moduleEdges": [], "circularDependencies": []}
        )


@pytest.mark.asyncio
async def test_an_empty_model_produces_an_honest_empty_report() -> None:
    tool = DocumentationGenerationToolEntrypoint()

    outputs = await tool.execute({"modules": [], "moduleEdges": [], "circularDependencies": []})

    DocumentationGenerationOutput.model_validate(outputs)
    assert outputs["moduleCount"] == 0
    assert outputs["circularDependencyCount"] == 0
    assert outputs["trust"] == "untrusted"
    assert "No modules were found" in outputs["markdown"]
    assert "No inter-module dependencies were found" in outputs["markdown"]
    assert "No circular dependencies were detected." in outputs["markdown"]
    assert "No module reaches the high-coupling threshold" in outputs["markdown"]


@pytest.mark.asyncio
async def test_real_modules_and_edges_appear_in_the_markdown_tables() -> None:
    tool = DocumentationGenerationToolEntrypoint()
    modules = [_module("api", 0, 1), _module("core", 1, 0)]
    module_edges = [{"from": "api", "to": "core", "fileEdgeCount": 3}]

    outputs = await tool.execute(
        {"modules": modules, "moduleEdges": module_edges, "circularDependencies": []}
    )

    markdown = outputs["markdown"]
    assert "| `api` | 0 | 1 |" in markdown
    assert "| `core` | 1 | 0 |" in markdown
    assert "| `api` | `core` | 3 |" in markdown
    assert outputs["moduleCount"] == 2


@pytest.mark.asyncio
async def test_a_real_circular_dependency_is_rendered_in_the_report() -> None:
    tool = DocumentationGenerationToolEntrypoint()
    circular_dependencies = [{"cycle": ["a", "b", "a"]}]

    outputs = await tool.execute(
        {"modules": [], "moduleEdges": [], "circularDependencies": circular_dependencies}
    )

    assert "`a` → `b` → `a`" in outputs["markdown"]
    assert outputs["circularDependencyCount"] == 1


@pytest.mark.asyncio
async def test_a_module_at_the_coupling_threshold_is_flagged() -> None:
    tool = DocumentationGenerationToolEntrypoint()
    # fanIn + fanOut == 5, exactly the disclosed threshold.
    modules = [_module("hub", 3, 2)]

    outputs = await tool.execute(
        {"modules": modules, "moduleEdges": [], "circularDependencies": []}
    )

    assert "`hub` — fan-in 3, fan-out 2 (total 5)" in outputs["markdown"]


@pytest.mark.asyncio
async def test_a_module_below_the_coupling_threshold_is_not_flagged() -> None:
    tool = DocumentationGenerationToolEntrypoint()
    modules = [_module("quiet", 1, 1)]

    outputs = await tool.execute(
        {"modules": modules, "moduleEdges": [], "circularDependencies": []}
    )

    assert "quiet" not in outputs["markdown"].split("High-Coupling Modules")[1]


@pytest.mark.asyncio
async def test_every_real_output_is_genuinely_tagged_untrusted() -> None:
    """FR-059's own invariant, reused here since this Tool also derives
    entirely from ingested-repository-sourced content."""
    tool = DocumentationGenerationToolEntrypoint()

    outputs = await tool.execute({"modules": [], "moduleEdges": [], "circularDependencies": []})

    assert outputs["trust"] == "untrusted"


def test_input_and_output_models_document_the_tool_contract() -> None:
    DocumentationGenerationOutput(
        markdown="# Architecture Documentation\n",
        module_count=0,
        circular_dependency_count=0,
        trust="untrusted",
    )
