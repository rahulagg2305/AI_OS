"""The `dependency.graph` Tool — this pack's third real increment
(`P05-S02-M32-T03`, FR-052: "Construct module and dependency graphs,"
acceptance criterion: "Graph artifact produced and queryable").

**Real, disclosed scope decision (`AskUserQuestion`): Python only, via
the real `ast` module, not regex heuristics or a shallow edge-free
graph.** A genuine dependency graph needs real import edges, which
needs real file *content*, not just the paths `repository.ingest`
already extracts — building that correctly for every language this
pack's own `language_detection.py` recognizes is real, substantial,
separate per-language work. Python's own stdlib `ast.parse()` gives
exact, not-heuristic parsing for the one language built here; other
languages are real, disclosed, deferred work, matching this project's
established "build the real, buildable subset" precedent
(`document_processing.md`'s own PDF/DOCX deferral).

**`tier1_sandboxed`, for the identical ADR-0016 reason
`repository_ingestion.py` already states — reading and parsing real
file *content* is "processing untrusted repository content," not the
path-only pattern-matching `language_detection.py` does (which is
`tier2_trusted`).** Both the file read and the `ast.parse()` call
happen *inside* the real sandboxed script below — only the derived,
structural result (module names, edges — never raw source text) ever
crosses back into this pack's own trusted process memory.

**Scope is caller-supplied (`pythonFiles`), not re-discovered.** This
Tool does not re-walk the repository itself — the identical
"reuse `repository.ingest`'s own output, no parallel mechanism"
precedent `language_detection.py` already establishes: a real caller
passes the subset of `repository.ingest`'s own `files` output already
classified `language == "python"`.

**Real, disclosed limitations of the module-name resolution, not
silently assumed correct for every repo layout:** module dotted names
are derived naively from each file's own repo-relative path (treating
the repository root as the import root) — correct for a typical flat
package layout, but not for a `src/`-rooted package or a namespace
package that omits `__init__.py`. An import this heuristic cannot
resolve to a known internal module is reported honestly in
`unresolvedImports`, never guessed into a fabricated edge. A file that
fails to parse (a syntax error, a non-UTF-8 file) is reported in
`parseErrors`, and the rest of the graph is still produced — one bad
file does not fail the whole call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_pack_project_intelligence.provenance import DERIVED_CONTENT_TRUST, Trust
from ai_os_sdk.models.tool import TrustTier

# A real, dependency-free, stdlib-only script — see
# `repository_ingestion.py`'s own `_INGEST_SCRIPT` docstring note for
# why this cannot import anything from this pack's own `src/` tree (a
# separate process, a separate filesystem entirely).
_GRAPH_SCRIPT = """
import ast
import json
import sys


def module_name_for(path):
    without_ext = path[:-3] if path.endswith(".py") else path
    parts = without_ext.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def package_parts_for(path):
    parts = path[:-3].split("/") if path.endswith(".py") else path.split("/")
    if parts and parts[-1] == "__init__":
        return parts[:-1]
    return parts[:-1]


def resolve_relative(importing_path, level, module):
    parts = package_parts_for(importing_path)
    for _ in range(level - 1):
        if parts:
            parts.pop()
    if module:
        parts = parts + module.split(".")
    return ".".join(parts)


def resolve_internal(dotted_name, known_modules):
    if not dotted_name:
        return None
    parts = dotted_name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known_modules:
            return candidate
        parts.pop()
    return None


python_files = json.loads(sys.stdin.read())
module_by_name = {module_name_for(path): path for path in python_files}
known_modules = set(module_by_name)

nodes = [{"path": path} for path in python_files]
edges = []
unresolved = []
parse_errors = []


def record(path, dotted_name):
    resolved = resolve_internal(dotted_name, known_modules)
    if resolved is not None and module_by_name[resolved] != path:
        edges.append({"from": path, "to": module_by_name[resolved], "importedName": dotted_name})
    elif resolved is None:
        unresolved.append({"from": path, "importedName": dotted_name})


for path in python_files:
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        parse_errors.append({"path": path, "error": f"{type(exc).__name__}: {exc}"})
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(path, alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base_module = resolve_relative(path, node.level, node.module)
            else:
                base_module = node.module
            for alias in node.names:
                specific = f"{base_module}.{alias.name}" if base_module else alias.name
                if resolve_internal(specific, known_modules) is not None:
                    record(path, specific)
                elif base_module and resolve_internal(base_module, known_modules) is not None:
                    record(path, base_module)
                else:
                    record(path, specific)

result = {
    "nodes": nodes,
    "edges": edges,
    "unresolvedImports": unresolved,
    "parseErrors": parse_errors,
}
print(json.dumps(result))
"""

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "importedName": {"type": "string"},
                },
                "required": ["from", "to", "importedName"],
            },
        },
        "unresolvedImports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "importedName": {"type": "string"},
                },
                "required": ["from", "importedName"],
            },
        },
        "parseErrors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "error": {"type": "string"},
                },
                "required": ["path", "error"],
            },
        },
        "trust": {"type": "string", "enum": ["trusted", "untrusted"]},
    },
    "required": ["nodes", "edges", "unresolvedImports", "parseErrors", "trust"],
    "additionalProperties": False,
}

_REQUIRED_INVOCATION_FIELDS = (
    "workingDirectory",
    "pythonFiles",
    "timeoutSeconds",
    "maxOutputBytes",
)


class DependencyGraphToolInputError(ValueError):
    """This tool's inputs were missing a required field, a real sandbox
    had not yet been injected, or the real sandboxed parse itself
    failed or produced output that could not be parsed as the declared
    graph artifact — the same real-input-validation contract every
    Tool in this project already enforces for its own inputs."""


class DependencyGraphInput(BaseModel):
    """Documents this Tool's own manifest-declarable `inputSchema`
    reference target."""

    working_directory: str = Field(..., alias="workingDirectory")
    python_files: list[str] = Field(..., alias="pythonFiles")
    timeout_seconds: float = Field(..., alias="timeoutSeconds")
    max_output_bytes: int = Field(..., alias="maxOutputBytes")

    model_config = {"populate_by_name": True}


class GraphNode(BaseModel):
    path: str


class GraphEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    imported_name: str = Field(..., alias="importedName")

    model_config = {"populate_by_name": True}


class UnresolvedImport(BaseModel):
    from_: str = Field(..., alias="from")
    imported_name: str = Field(..., alias="importedName")

    model_config = {"populate_by_name": True}


class ParseError(BaseModel):
    path: str
    error: str


class DependencyGraphOutput(BaseModel):
    """Documents this Tool's own manifest-declarable `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    unresolved_imports: list[UnresolvedImport] = Field(..., alias="unresolvedImports")
    parse_errors: list[ParseError] = Field(..., alias="parseErrors")
    trust: Trust

    model_config = {"populate_by_name": True}


class DependencyGraphToolEntrypoint:
    """The manifest's own future `tools[].entrypoint` for
    `dependency.graph` — zero-argument-constructible, no
    `PackContextReceiver` needed (only a directly-injected `sandbox`,
    the identical shape `repository_ingestion.py` already
    establishes)."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self.sandbox: Any = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        working_directory = inputs.get("workingDirectory")
        python_files = inputs.get("pythonFiles")
        timeout_seconds = inputs.get("timeoutSeconds")
        max_output_bytes = inputs.get("maxOutputBytes")
        missing = [
            name
            for name, value in zip(
                _REQUIRED_INVOCATION_FIELDS,
                (working_directory, python_files, timeout_seconds, max_output_bytes),
                strict=True,
            )
            if value is None
        ]
        if missing:
            raise DependencyGraphToolInputError(
                f"DependencyGraphToolEntrypoint requires "
                f"{', '.join(_REQUIRED_INVOCATION_FIELDS)} in its inputs — "
                f"missing: {', '.join(missing)}"
            )
        if not isinstance(python_files, list) or not all(
            isinstance(path, str) for path in python_files
        ):
            raise DependencyGraphToolInputError(
                "DependencyGraphToolEntrypoint requires 'pythonFiles' to be a list of strings"
            )
        if self.sandbox is None:
            raise DependencyGraphToolInputError(
                "DependencyGraphToolEntrypoint.execute() called before a real sandbox was "
                "injected — a real caller (SqlToolRegistry.resolve_tool) always injects one "
                "for a tier1_sandboxed tool before returning it"
            )
        assert isinstance(working_directory, str)  # noqa: S101
        assert isinstance(timeout_seconds, (int, float))  # noqa: S101
        assert isinstance(max_output_bytes, int)  # noqa: S101

        result = await self.sandbox.execute(
            command=[*self.sandbox.python_command, "-c", _GRAPH_SCRIPT],
            working_directory=Path(working_directory),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            stdin=json.dumps(python_files).encode("utf-8"),
        )
        if result.timed_out:
            raise DependencyGraphToolInputError(
                f"DependencyGraphToolEntrypoint timed out analyzing {len(python_files)} file(s) "
                f"after {timeout_seconds}s"
            )
        if result.exit_code != 0:
            raise DependencyGraphToolInputError(
                f"DependencyGraphToolEntrypoint could not build the graph: exit code "
                f"{result.exit_code}, stderr: {result.stderr.strip()}"
            )
        if result.truncated:
            raise DependencyGraphToolInputError(
                f"DependencyGraphToolEntrypoint's output exceeded "
                f"maxOutputBytes={max_output_bytes} and was truncated — the graph is "
                "incomplete; raise maxOutputBytes and retry rather than trust a cut-off result"
            )
        try:
            parsed = dict(json.loads(result.stdout))
        except json.JSONDecodeError as exc:
            raise DependencyGraphToolInputError(
                f"DependencyGraphToolEntrypoint's sandboxed parse produced output that was "
                f"not valid JSON: {exc}"
            ) from exc
        parsed["trust"] = DERIVED_CONTENT_TRUST
        return parsed
