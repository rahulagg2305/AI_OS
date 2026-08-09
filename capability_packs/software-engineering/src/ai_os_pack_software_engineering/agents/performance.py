"""The Performance Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Performance entry (FR-044, explicitly
`LATER`/post-v1 in `functional_requirements.md` — the only such
requirement in the whole 75-FR backlog; built now because its own
roadmap ticket, `P08-S01-M29-T07`, was the single remaining ready Task
above post-v1 priority once every other ready Task was exhausted).

**"A running system" (this ticket's own literal Input) reduced
honestly to "one real source file from that system" — the identical
single-file scope discipline every sibling agent in this pack already
establishes (`build`/`lint`/`qa-test`/`code-review`/`refactoring`).**
This agent has no real APM/instrumentation infrastructure to attach to
a genuinely *running* process (none exists anywhere in this codebase),
so "performance" here means real, static, deterministic complexity
analysis — a real, honest proxy for where runtime cost is *likely* to
concentrate (more decision paths through a function generally means
more to execute, and more to optimize), not a measured runtime
profile. Disclosed plainly, not fabricated as something it is not.

**Deliberately no LLM call at all — the identical `lint`/`qa-test`
shape, not `code-review`/`refactoring`'s own LLM-backed shape.**
Cyclomatic complexity (McCabe, 1976) is computed directly from the
file's own real AST (stdlib `ast`, the identical "real, deterministic,
no LLM guess" mechanism Project Intelligence's own
`dependency.graph`/`architecture.recover` tools already establish for
unrelated static analysis) — every recommendation this agent produces
is a mechanical consequence of a real, inspectable number crossing a
real, named threshold, never an LLM's own opinion about a file it may
not have even read correctly.

**Read-only, matching `code_review.py`'s own read mechanism — never
writes anything.** A performance report has no file to produce beyond
its own return value.
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)

_READ_TIMEOUT_SECONDS = 10.0
_READ_MAX_OUTPUT_BYTES = 65536

# McCabe's own original, widely-cited "10" — real, named, industry-
# standard threshold above which a function is conventionally
# considered complex enough to warrant decomposition, not an arbitrary
# guess.
_COMPLEXITY_THRESHOLD = 10

_READ_FILE_SCRIPT = (
    "import pathlib, sys\nsys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())\n"
)

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string"},
        "lineCount": {"type": "integer"},
        "functionCount": {"type": "integer"},
        "hotspots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "lineNumber": {"type": "integer"},
                    "complexity": {"type": "integer"},
                },
                "required": ["name", "lineNumber", "complexity"],
                "additionalProperties": False,
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["filePath", "lineCount", "functionCount", "hotspots", "recommendations"],
    "additionalProperties": False,
}

_REQUIRED_FIELDS = ("workingDirectory", "filePath")


class PerformanceInstructionError(Exception):
    """This agent's own invocation contract was violated (called
    before :meth:`bind_pack_context`, missing a required field), or
    ``filePath`` does not resolve to a real, existing, syntactically
    valid Python file inside ``workingDirectory``. Raised clearly,
    before — or in place of — any sandbox call."""


class PerformanceAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). Field names deliberately match
    `LintAgentInput`'s own ``workingDirectory``/``filePath``."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")

    model_config = {"populate_by_name": True}


class PerformanceHotspot(BaseModel):
    """One real function's own real, computed cyclomatic complexity —
    never an LLM's guess at which function "looks" complex."""

    name: str
    line_number: int = Field(..., alias="lineNumber")
    complexity: int

    model_config = {"populate_by_name": True}


class PerformanceAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs."
    Mirrors the real fields :meth:`PerformanceAgentEntrypoint.execute`
    returns. ``recommendations`` is mechanically derived from
    ``hotspots`` crossing :data:`_COMPLEXITY_THRESHOLD` — never
    separately authored."""

    file_path: str = Field(..., alias="filePath")
    line_count: int = Field(..., alias="lineCount")
    function_count: int = Field(..., alias="functionCount")
    hotspots: list[PerformanceHotspot]
    recommendations: list[str]

    model_config = {"populate_by_name": True}


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to `lint.py`'s/`verification.py`'s own helper of the
    same name — duplicated, not imported (this pack's own established
    "no shared module needed for a single real caller each" reason)."""
    stripped = raw_path.strip()
    if not stripped:
        raise PerformanceInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise PerformanceInstructionError(
            f"filePath {raw_path!r} resolves outside {working_directory}"
        )
    if not resolved_target.is_file():
        raise PerformanceInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str]:
    """Identical dual-path shape to `lint.py`'s own ``_extract_payload``
    — direct fields, or, when absent, parsed as JSON from the Context
    Manager's own assembled ``context``."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise PerformanceInstructionError(
                "PerformanceAgentEntrypoint requires 'workingDirectory' and 'filePath' — "
                "either directly in inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PerformanceInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise PerformanceInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory' or 'filePath'"
            )

    working_directory, file_path = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise PerformanceInstructionError("workingDirectory and filePath must both be strings")
    return working_directory, file_path


def _cyclomatic_complexity(node: ast.AST) -> int:
    """McCabe cyclomatic complexity: 1 plus one for every real,
    independent decision point inside ``node`` — the standard formula,
    not a novel approximation. Counts ``if``/``for``/``while``/``try``/
    ``except``/``with`` blocks, each real boolean operator combination
    beyond the first operand (``a and b and c`` has two real, distinct
    short-circuit paths beyond the first), and each comprehension's own
    implicit loop."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.Try,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
            ),
        ):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1
    return complexity


class _Hotspot(TypedDict):
    name: str
    lineNumber: int
    complexity: int


def compute_performance_report(source: str, file_path: str) -> dict[str, Any]:
    """The one real, pure computation this agent performs — a plain
    function so it is independently unit-testable without any sandbox
    or `PackContext` at all."""
    tree = ast.parse(source)
    functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    hotspots: list[_Hotspot] = sorted(
        (
            _Hotspot(name=fn.name, lineNumber=fn.lineno, complexity=_cyclomatic_complexity(fn))
            for fn in functions
        ),
        key=lambda h: h["complexity"],
        reverse=True,
    )
    recommendations = [
        f"Function '{h['name']}' (line {h['lineNumber']}) has cyclomatic complexity "
        f"{h['complexity']}, exceeding the recommended threshold of {_COMPLEXITY_THRESHOLD} — "
        "consider decomposing it."
        for h in hotspots
        if h["complexity"] > _COMPLEXITY_THRESHOLD
    ]
    return {
        "filePath": file_path,
        "lineCount": len(source.splitlines()),
        "functionCount": len(functions),
        "hotspots": hotspots,
        "recommendations": recommendations,
    }


class PerformanceAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Performance
    Agent — zero-argument-constructible like every other agent in this
    pack. Implements :class:`~ai_os_sdk.contracts.Agent` +
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
    directly — no ``ai_os_kernel`` import anywhere, satisfying check 7
    from the start."""

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        timeout_seconds: float = _READ_TIMEOUT_SECONDS,
        max_output_bytes: int = _READ_MAX_OUTPUT_BYTES,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.tools is None:
            raise PerformanceInstructionError(
                "PerformanceAgentEntrypoint.execute() called before bind_pack_context() bound "
                "a PackContext granting the sandbox:execute permission (context.tools) — a "
                "real caller must inject one before first use"
            )

        working_directory_raw, file_path_raw = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        if not await asyncio.to_thread(working_directory.is_dir):
            raise PerformanceInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, file_path_raw)

        read_result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", _READ_FILE_SCRIPT, file_path_raw],
                "working_directory": str(working_directory),
                "timeout_seconds": self._timeout_seconds,
                "max_output_bytes": self._max_output_bytes,
            },
        )
        if read_result.exit_code != 0:
            raise PerformanceInstructionError(
                f"could not read {file_path_raw!r} inside the sandbox: {read_result.stderr}"
            )

        try:
            return compute_performance_report(read_result.stdout, file_path_raw)
        except SyntaxError as exc:
            raise PerformanceInstructionError(
                f"{file_path_raw!r} is not syntactically valid Python: {exc}"
            ) from exc
