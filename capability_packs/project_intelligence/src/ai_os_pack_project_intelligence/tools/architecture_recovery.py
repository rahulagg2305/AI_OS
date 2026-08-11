"""The `architecture.recover` Tool — this pack's fourth real increment
(`P05-S02-M32-T04`, FR-053: "Recover architectural boundaries and
produce architecture documentation," acceptance criterion:
"Architecture recovery artifact produced").

**Real, disclosed scope decision (`AskUserQuestion`): deterministic
graph analysis, not LLM-driven narrative documentation.** A genuine
architecture-recovery *narrative* (naming layers, describing intent)
needs real LLM reasoning — a real Agent, the first one this pack would
ever build, a materially bigger design investment (prompts, LLM
Gateway wiring, a new kind of output entirely). What is genuinely
buildable *mechanically*, from `dependency.graph`'s own real output
alone, is real: module-level boundary aggregation, real circular-
dependency detection (a genuine architectural smell — a real graph
cycle, not a heuristic), and real fan-in/fan-out coupling metrics. This
mirrors the identical "Tool, not Agent" decision `repository_ingestion.py`/
`language_detection.py`/`dependency_graph.py` already made, each via
its own `AskUserQuestion`.

**`tier2_trusted`, not `tier1_sandboxed` — the identical reasoning
`language_detection.py` already establishes.** This Tool never touches
a filesystem, network, or executes anything; its only input is
`dependency.graph`'s own already-derived `nodes`/`edges` (file paths
and import names, not raw file content) — pattern-matching and graph
traversal over already-safe, already-extracted structural data.

**Module boundaries are derived from each file's own top-level
directory** — the identical convention `repository_ingestion.py`'s own
`modules` field already establishes (`"."` for a root-level file) —
recomputed here directly from each node's `path` rather than requiring
a second, redundant input, since it is a one-line, already-documented
rule, not real logic worth passing across a Tool boundary.

**Circular dependencies are detected at the module level, not the file
level.** A cycle between two files in the same module is normal,
expected code structure, not an architectural boundary violation; a
cycle between two distinct top-level modules is the real, actionable
signal FR-053's own "architectural boundaries" language points at.

**Real, disclosed limitation of the cycle search, not silently assumed
exhaustive:** it is a real, deterministic DFS that finds every simple
cycle reachable from each module in turn (never double-reporting the
same cycle from a different starting point) — correct and complete for
every real module count this pack has ever been tested against. It is
not Johnson's algorithm; a pathological graph with an exponential
number of simple cycles could make this slower than a dedicated
cycle-enumeration algorithm would be. Real module-level dependency
graphs are small (tens, not millions, of top-level directories), so
this trade-off is disclosed, not hidden, rather than pre-optimized for
a case this pack has no real evidence it will ever meet.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_os_pack_project_intelligence.provenance import DERIVED_CONTENT_TRUST, Trust
from ai_os_sdk.models.tool import TrustTier


def _module_for(path: str) -> str:
    return path.split("/")[0] if "/" in path else "."


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fanIn": {"type": "integer"},
                    "fanOut": {"type": "integer"},
                },
                "required": ["name", "fanIn", "fanOut"],
            },
        },
        "moduleEdges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "fileEdgeCount": {"type": "integer"},
                },
                "required": ["from", "to", "fileEdgeCount"],
            },
        },
        "circularDependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cycle": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cycle"],
            },
        },
        "trust": {"type": "string", "enum": ["trusted", "untrusted"]},
    },
    "required": ["modules", "moduleEdges", "circularDependencies", "trust"],
    "additionalProperties": False,
}


class ArchitectureRecoveryToolInputError(ValueError):
    """This tool's inputs were missing the required `nodes`/`edges`
    fields, or they were not the shape `dependency.graph`'s own output
    already produces — the same real-input-validation contract every
    Tool in this project already enforces for its own inputs."""


def _find_cycles(module_edges: dict[str, set[str]]) -> list[list[str]]:
    """Real DFS-based cycle detection over the module-level dependency
    graph — a standard, deterministic algorithm, not a heuristic. Each
    real cycle is reported exactly once, starting from its
    lexicographically smallest node, so the same cycle found via two
    different starting points is not double-reported."""
    cycles: list[list[str]] = []
    seen_cycle_keys: set[tuple[str, ...]] = set()

    def dfs(start: str, node: str, path: list[str], on_path: set[str]) -> None:
        for neighbor in sorted(module_edges.get(node, set())):
            if neighbor == start and len(path) > 1:
                key = tuple(path)
                if key not in seen_cycle_keys:
                    seen_cycle_keys.add(key)
                    cycles.append([*path, start])
            elif neighbor not in on_path and neighbor >= start:
                dfs(start, neighbor, [*path, neighbor], on_path | {neighbor})

    for module in sorted(module_edges):
        dfs(module, module, [module], {module})

    return cycles


class _NodeInput(BaseModel):
    """One entry of this Tool's required `nodes` input — the exact shape
    `dependency.graph`'s own `GraphNode` output already produces (mirrored
    locally, not imported, the identical `FileEntryInput`/`repository.
    ingest` precedent every other Tool in this pack already follows)."""

    path: str


class _EdgeInput(BaseModel):
    """One entry of `edges` — the exact shape `dependency.graph`'s own
    `GraphEdge` output already produces (`from`/`to`/`importedName`)."""

    from_: str = Field(..., alias="from")
    to: str
    imported_name: str = Field(..., alias="importedName")

    model_config = {"populate_by_name": True}


class ArchitectureRecoveryInput(BaseModel):
    """Documents this Tool's own manifest-declarable `inputSchema`
    reference target — the exact `nodes`/`edges` shape `dependency.graph`'s
    own output produces (`P05-S02-M32-T07`: added so this already-real Tool
    is declarable, since `manifest.schema.json` requires a real `inputSchema`
    Pydantic model per tool; `execute` is unchanged — this model is the
    declared input contract, not a new runtime validator, the identical
    role `LanguageDetectionInput` already plays for `language.detect`)."""

    nodes: list[_NodeInput]
    edges: list[_EdgeInput]


class ArchitectureRecoveryOutput(BaseModel):
    """Documents this Tool's own manifest-declarable `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    modules: list[dict[str, Any]]
    module_edges: list[dict[str, Any]] = Field(..., alias="moduleEdges")
    circular_dependencies: list[dict[str, Any]] = Field(..., alias="circularDependencies")
    trust: Trust

    model_config = {"populate_by_name": True}


class ArchitectureRecoveryToolEntrypoint:
    """The manifest's own future `tools[].entrypoint` for
    `architecture.recover` — zero-argument-constructible, no injected
    collaborator of any kind needed (no sandbox, no
    `PackContextReceiver`): pure, deterministic computation over its
    own `inputs`."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        nodes = inputs.get("nodes")
        edges = inputs.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ArchitectureRecoveryToolInputError(
                "ArchitectureRecoveryToolEntrypoint requires 'nodes' and 'edges' "
                "(the same shape dependency.graph's own output already produces) "
                "in its inputs"
            )
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("path"), str):
                raise ArchitectureRecoveryToolInputError(
                    f"ArchitectureRecoveryToolEntrypoint requires every 'nodes' entry to be "
                    f"{{'path': str}} — got {node!r}"
                )
        for edge in edges:
            if (
                not isinstance(edge, dict)
                or not isinstance(edge.get("from"), str)
                or not isinstance(edge.get("to"), str)
            ):
                raise ArchitectureRecoveryToolInputError(
                    f"ArchitectureRecoveryToolEntrypoint requires every 'edges' entry to be "
                    f"{{'from': str, 'to': str, ...}} — got {edge!r}"
                )

        all_modules = {_module_for(node["path"]) for node in nodes}

        module_edge_counts: dict[tuple[str, str], int] = {}
        for edge in edges:
            from_module = _module_for(edge["from"])
            to_module = _module_for(edge["to"])
            if from_module == to_module:
                continue
            key = (from_module, to_module)
            module_edge_counts[key] = module_edge_counts.get(key, 0) + 1

        module_edges = [
            {"from": from_module, "to": to_module, "fileEdgeCount": count}
            for (from_module, to_module), count in sorted(module_edge_counts.items())
        ]

        adjacency: dict[str, set[str]] = {}
        for from_module, to_module in module_edge_counts:
            adjacency.setdefault(from_module, set()).add(to_module)

        fan_out: dict[str, int] = {module: 0 for module in all_modules}
        fan_in: dict[str, int] = {module: 0 for module in all_modules}
        for from_module, to_module in module_edge_counts:
            fan_out[from_module] += 1
            fan_in[to_module] += 1

        modules = [
            {"name": name, "fanIn": fan_in[name], "fanOut": fan_out[name]}
            for name in sorted(all_modules)
        ]

        cycles = _find_cycles(adjacency)
        circular_dependencies = [{"cycle": cycle} for cycle in cycles]

        return {
            "modules": modules,
            "moduleEdges": module_edges,
            "circularDependencies": circular_dependencies,
            "trust": DERIVED_CONTENT_TRUST,
        }
