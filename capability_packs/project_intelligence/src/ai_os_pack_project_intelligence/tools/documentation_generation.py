"""The `documentation.generate` Tool — this pack's fifth real
increment (`P05-S02-M32-T05`, FR-056: "Generate documentation for a
poorly documented system," acceptance criterion: "Documentation set
produced for a real repository").

**Real, disclosed scope decision (`AskUserQuestion`): a deterministic
Markdown report rendered from `architecture.recover`'s own already-real
facts, not LLM-written semantic prose.** Genuine documentation
describing what a module's code actually *does* needs an LLM reading
real code content — a real Agent, the first this pack would ever
build, the identical bigger-investment fork already raised and
deferred for `architecture.recover` itself. What this Tool renders
instead is real, honest, *structural* documentation: a module overview,
a dependency table, and an "Architectural Concerns" section — every
fact already computed by `architecture.recover`, never invented. This
mirrors the identical "Tool, not Agent" decision every other Tool in
this module has made, each via its own `AskUserQuestion`.

**"A documentation set" (FR-056's own plural wording), honestly
satisfied as one real artifact with distinct, real sections** — Module
Overview, Module Dependencies, Architectural Concerns — rather than
fabricating multiple separate files for no real reason none of this
Tool's own real input would ever justify.

**`tier2_trusted`, not `tier1_sandboxed` — the identical reasoning
`language_detection.py`/`architecture_recovery.py` already establish.**
This Tool never touches a filesystem, network, or executes anything;
its only input is `architecture.recover`'s own already-derived
`modules`/`moduleEdges`/`circularDependencies`.

**The high-coupling threshold is a named, documented constant
(:data:`_HIGH_COUPLING_THRESHOLD`), not silently hardcoded, disclosed
exactly like `language_detection.py`'s own confidence threshold** — a
real, honest editorial judgment this report has to make somewhere
("which modules are worth flagging"), stated plainly rather than
buried inside the render logic.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_os_pack_project_intelligence.provenance import DERIVED_CONTENT_TRUST, Trust
from ai_os_sdk.models.tool import TrustTier

# Named, documented, real editorial threshold — a module whose combined
# fan-in + fan-out reaches this many real, distinct module-level
# dependencies is flagged as high-coupling. Not caller-configurable:
# offering a parameter here would let a caller quietly tune away a real
# finding rather than address it.
_HIGH_COUPLING_THRESHOLD = 5

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "markdown": {"type": "string"},
        "moduleCount": {"type": "integer"},
        "circularDependencyCount": {"type": "integer"},
        "trust": {"type": "string", "enum": ["trusted", "untrusted"]},
    },
    "required": ["markdown", "moduleCount", "circularDependencyCount", "trust"],
    "additionalProperties": False,
}


class DocumentationGenerationToolInputError(ValueError):
    """This tool's inputs were missing the required `modules`/
    `moduleEdges`/`circularDependencies` fields, or they were not the
    shape `architecture.recover`'s own output already produces — the
    same real-input-validation contract every Tool in this project
    already enforces for its own inputs."""


def _render_module_overview(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return "_No modules were found in the recovered model._\n"
    lines = ["| Module | Fan-In | Fan-Out |", "|---|---|---|"]
    for module in modules:
        lines.append(f"| `{module['name']}` | {module['fanIn']} | {module['fanOut']} |")
    return "\n".join(lines) + "\n"


def _render_module_dependencies(module_edges: list[dict[str, Any]]) -> str:
    if not module_edges:
        return "_No inter-module dependencies were found in the recovered model._\n"
    lines = ["| From | To | File-Level Edges |", "|---|---|---|"]
    for edge in module_edges:
        lines.append(f"| `{edge['from']}` | `{edge['to']}` | {edge['fileEdgeCount']} |")
    return "\n".join(lines) + "\n"


def _render_circular_dependencies(circular_dependencies: list[dict[str, Any]]) -> str:
    if not circular_dependencies:
        return "No circular dependencies were detected.\n"
    lines = []
    for entry in circular_dependencies:
        lines.append("- " + " → ".join(f"`{name}`" for name in entry["cycle"]))
    return "\n".join(lines) + "\n"


def _render_high_coupling_modules(modules: list[dict[str, Any]]) -> str:
    flagged = [
        module
        for module in modules
        if module["fanIn"] + module["fanOut"] >= _HIGH_COUPLING_THRESHOLD
    ]
    if not flagged:
        return (
            f"No module reaches the high-coupling threshold "
            f"(fan-in + fan-out ≥ {_HIGH_COUPLING_THRESHOLD}).\n"
        )
    lines = []
    for module in sorted(flagged, key=lambda m: -(m["fanIn"] + m["fanOut"])):
        total = module["fanIn"] + module["fanOut"]
        lines.append(
            f"- `{module['name']}` — fan-in {module['fanIn']}, fan-out "
            f"{module['fanOut']} (total {total})"
        )
    return "\n".join(lines) + "\n"


def _render_markdown(
    modules: list[dict[str, Any]],
    module_edges: list[dict[str, Any]],
    circular_dependencies: list[dict[str, Any]],
) -> str:
    sections = [
        "# Architecture Documentation",
        "",
        "_Generated structurally from a real, recovered dependency and "
        "coupling model — not a semantic description of what this code "
        "does._",
        "",
        "## Module Overview",
        "",
        _render_module_overview(modules),
        "## Module Dependencies",
        "",
        _render_module_dependencies(module_edges),
        "## Architectural Concerns",
        "",
        "### Circular Dependencies",
        "",
        _render_circular_dependencies(circular_dependencies),
        "### High-Coupling Modules",
        "",
        _render_high_coupling_modules(modules),
    ]
    return "\n".join(sections)


class _ModuleInput(BaseModel):
    """One entry of this Tool's required `modules` input — the exact shape
    `architecture.recover`'s own output already produces (`name`/`fanIn`/
    `fanOut`); mirrored locally, the identical `FileEntryInput` precedent."""

    name: str
    fan_in: int = Field(..., alias="fanIn")
    fan_out: int = Field(..., alias="fanOut")

    model_config = {"populate_by_name": True}


class DocumentationGenerationInput(BaseModel):
    """Documents this Tool's own manifest-declarable `inputSchema`
    reference target — the exact `modules`/`moduleEdges`/`circularDependencies`
    shape `architecture.recover`'s own output produces (`P05-S02-M32-T07`:
    added so this already-real Tool is declarable, since `manifest.schema.
    json` requires a real `inputSchema` Pydantic model per tool; `execute`
    is unchanged — this is the declared input contract, not a new runtime
    validator, the same role `LanguageDetectionInput` plays for
    `language.detect`). `moduleEdges`/`circularDependencies` stay
    `list[dict[str, Any]]` because `execute` itself consumes them loosely,
    only `modules` field-by-field — the model describes what the Tool
    genuinely reads, not a stricter shape it does not enforce."""

    modules: list[_ModuleInput]
    module_edges: list[dict[str, Any]] = Field(..., alias="moduleEdges")
    circular_dependencies: list[dict[str, Any]] = Field(..., alias="circularDependencies")

    model_config = {"populate_by_name": True}


class DocumentationGenerationOutput(BaseModel):
    """Documents this Tool's own manifest-declarable `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    markdown: str
    module_count: int = Field(..., alias="moduleCount")
    circular_dependency_count: int = Field(..., alias="circularDependencyCount")
    trust: Trust

    model_config = {"populate_by_name": True}


class DocumentationGenerationToolEntrypoint:
    """The manifest's own future `tools[].entrypoint` for
    `documentation.generate` — zero-argument-constructible, no
    injected collaborator of any kind needed (no sandbox, no
    `PackContextReceiver`): pure, deterministic rendering over its own
    `inputs`."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        modules = inputs.get("modules")
        module_edges = inputs.get("moduleEdges")
        circular_dependencies = inputs.get("circularDependencies")
        if (
            not isinstance(modules, list)
            or not isinstance(module_edges, list)
            or not isinstance(circular_dependencies, list)
        ):
            raise DocumentationGenerationToolInputError(
                "DocumentationGenerationToolEntrypoint requires 'modules', 'moduleEdges', "
                "and 'circularDependencies' (the same shape architecture.recover's own "
                "output already produces) in its inputs"
            )
        for module in modules:
            if (
                not isinstance(module, dict)
                or not isinstance(module.get("name"), str)
                or not isinstance(module.get("fanIn"), int)
                or not isinstance(module.get("fanOut"), int)
            ):
                raise DocumentationGenerationToolInputError(
                    f"DocumentationGenerationToolEntrypoint requires every 'modules' entry "
                    f"to be {{'name': str, 'fanIn': int, 'fanOut': int}} — got {module!r}"
                )

        markdown = _render_markdown(modules, module_edges, circular_dependencies)
        return {
            "markdown": markdown,
            "moduleCount": len(modules),
            "circularDependencyCount": len(circular_dependencies),
            "trust": DERIVED_CONTENT_TRUST,
        }
