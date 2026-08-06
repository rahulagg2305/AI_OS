"""The Security Analysis Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Security entry, FR-040 ("Perform
security analysis of generated code... Security gate result recorded
with findings"). This pack's tenth agent, and the third genuinely new
agent (not a migration) since the module-27 Platform SDK hard gate
lifted.

**Deliberately near-identical to `lint.py`'s own `LintAgentEntrypoint`
— not accidental duplication, the same "no shared module needed for a
single real caller each" reasoning `lint.py`'s own docstring already
applies.** Genuinely runs a real check inside the sandbox and reports
the real pass/fail outcome, derived only from the check's own exit
code — never from an LLM's opinion, the identical principle every
other quality-gate-shaped agent in this pack (`lint`, `qa-test`)
already establishes.

**A genuine design fork was found and resolved before writing this
module (product-owner decision, 2026-08-06): which real tool performs
the check.** `bandit` — the natural choice for real Python security
static analysis — is not available anywhere this agent could run: not
in this workspace's own dev venv, and (mirroring `lint.py`'s own
already-discovered `ruff` constraint exactly) almost certainly not in
`DockerSandbox`'s own default `python:3.12-slim` image either, with no
dependency-install step anywhere in this codebase to put it there
(the identical real gap `lint.py`'s own docstring names). Three real
options existed: (1) a hand-written stdlib `ast`-based heuristic check,
run through the sandbox exactly like `lint.py`'s own `py_compile`
call — no LLM, no new dependency, narrower than a real tool but honest
about that limit; (2) an LLM-based review — real and more semantically
capable, but a genuine, disclosed departure from this pack's own
"never an LLM's opinion" gate principle; (3) add `bandit` as a new
dependency now, usable immediately by `LocalSubprocessSandbox` but
leaving `DockerSandbox`'s own default image genuinely broken until a
custom pre-built image exists. **(1) was chosen** — the identical
reasoning `lint.py` already applied to the same class of problem: the
smallest real answer that works identically on every sandbox backend
this pipeline can actually run against, not the most thorough one.

**The check: a fixed, embedded stdlib `ast` scan (`_SCAN_SCRIPT`), not
a caller-supplied command** — unlike `lint.py`'s own `lintCommand`
(an arbitrary, caller-chosen argv), this agent's own check is not
externally parameterizable, since there is no external tool to name;
the script itself *is* the check. Detects four real, well-known,
AST-precise patterns, deliberately excluding fuzzier heuristics (e.g.
hardcoded-secret-shaped string literals) that would make findings
unreliable rather than real: `eval`/`exec` calls, `subprocess` calls
with `shell=True`, `pickle.load`/`pickle.loads` calls, and `yaml.load`
calls with no `Loader` keyword argument (an unsafe default in PyYAML
before 5.1, and still a real footgun since callers can omit it).

**Input/output contract mirrors `lint.py`'s own shape, minus
`lintCommand`** (there is nothing for a caller to choose) **and with
`findings` in place of `output`'s own free text** — this agent returns
real, structured data (`rule`/`line`/`message` per finding), not a raw
tool transcript, since the embedded script itself already emits
structured JSON rather than human-readable text. `passed` is
`exitCode == 0`, identical in spirit to every other real gate-shaped
agent in this pack — the script itself decides and exits, this module
never re-judges its output.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)

# Named, documented first-cut values — the identical "placeholder
# safety limit, not yet tuned" carve-out `lint.py`/`verification.py`
# already use.
_SCAN_TIMEOUT_SECONDS = 10.0
_SCAN_MAX_OUTPUT_BYTES = 65536

# The embedded, portable stdlib-only scan — executed inside the sandbox
# via `python -c`, never imported or run by this module's own process.
# Reads the target file's own source, parses it with `ast`, and prints
# exactly one JSON object (`{"findings": [...]}`)  to stdout, then exits
# 1 if any finding was recorded, 0 otherwise. No third-party import —
# the same "present in every Python installation this codebase could
# possibly run against" reasoning `lint.py`'s own `py_compile` choice
# already establishes.
_SCAN_SCRIPT = """
import ast, json, sys

class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings = []

    def visit_Call(self, node):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in ("eval", "exec"):
            self.findings.append({
                "rule": "dangerous-call",
                "line": node.lineno,
                "message": f"call to {name}() can execute arbitrary code",
            })
        elif name in ("call", "run", "Popen", "check_call", "check_output"):
            for kw in node.keywords:
                is_shell_true = (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                )
                if is_shell_true:
                    self.findings.append({
                        "rule": "subprocess-shell-true",
                        "line": node.lineno,
                        "message": f"{name}(..., shell=True) risks shell injection",
                    })
        elif name in ("load", "loads") and isinstance(func, ast.Attribute):
            base = getattr(func.value, "id", None)
            if base == "pickle":
                self.findings.append({
                    "rule": "unsafe-deserialization",
                    "line": node.lineno,
                    "message": f"pickle.{name}() can execute arbitrary code on untrusted input",
                })
            elif base == "yaml" and name == "load":
                has_loader = any(kw.arg == "Loader" for kw in node.keywords)
                if not has_loader:
                    self.findings.append({
                        "rule": "unsafe-yaml-load",
                        "line": node.lineno,
                        "message": "yaml.load() with no Loader= defaults to an unsafe loader",
                    })
        self.generic_visit(node)

source = open(sys.argv[1], encoding="utf-8").read()
tree = ast.parse(source, filename=sys.argv[1])
visitor = _Visitor()
visitor.visit(tree)
print(json.dumps({"findings": visitor.findings}))
sys.exit(1 if visitor.findings else 0)
"""

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "line": {"type": "integer"},
                    "message": {"type": "string"},
                },
                "required": ["rule", "line", "message"],
            },
        },
    },
    "required": ["passed", "exitCode", "findings"],
    "additionalProperties": False,
}


class SecurityAnalysisInstructionError(Exception):
    """This agent's input could not be turned into a safe, real run —
    a required field was missing or malformed, ``filePath`` does not
    resolve to a real, existing file inside ``workingDirectory``, or
    the scan script's own output could not be parsed as the documented
    JSON shape. Raised clearly, before or immediately after the sandbox
    call, never a silent, empty findings list."""


class SecurityAnalysisInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). Field names deliberately match
    ``BuildAgentOutput``'s own ``workingDirectory``/``filePath`` — the
    identical convention ``LintAgentInput``/``TestAgentInput`` already
    establish, since this agent is meant to consume a Build Agent
    result directly."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")

    model_config = {"populate_by_name": True}


class Finding(BaseModel):
    """One real, AST-precise finding the embedded scan script emitted —
    never fabricated or embellished by this module."""

    rule: str
    line: int
    message: str


class SecurityAnalysisOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs."
    Mirrors the real fields :meth:`SecurityAnalysisAgentEntrypoint.execute`
    returns — ``passed`` is derived only from ``exitCode``, never from
    any judgment about ``findings``' own content, the identical
    principle ``LintAgentOutput``'s own docstring already states."""

    passed: bool
    exit_code: int | None = Field(..., alias="exitCode")
    findings: list[Finding]

    model_config = {"populate_by_name": True}


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to `lint.py`'s/`verification.py`'s own helper of the
    same name — resolves ``raw_path`` against ``working_directory``,
    verifies it remains inside it, and verifies the resulting file
    genuinely exists."""
    stripped = raw_path.strip()
    if not stripped:
        raise SecurityAnalysisInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise SecurityAnalysisInstructionError(
            f"filePath {raw_path!r} resolves outside {working_directory}"
        )
    if not resolved_target.is_file():
        raise SecurityAnalysisInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


_REQUIRED_FIELDS = ("workingDirectory", "filePath")


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str]:
    """Identical fallback shape to `lint.py`'s own ``_extract_payload``
    — direct fields, or, when absent, parsed as JSON from the Context
    Manager's own assembled ``context``."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise SecurityAnalysisInstructionError(
                "SecurityAnalysisAgentEntrypoint requires 'workingDirectory' and 'filePath' "
                "— either directly in inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecurityAnalysisInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise SecurityAnalysisInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory' or 'filePath'"
            )

    working_directory, file_path = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise SecurityAnalysisInstructionError("workingDirectory and filePath must both be strings")
    return working_directory, file_path


class SecurityAnalysisAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Security
    Analysis Agent — zero-argument-constructible, trivially so here:
    nothing is built lazily, since this agent needs no LLM composition
    at all (the identical shape ``LintAgentEntrypoint``/
    ``TestAgentEntrypoint`` already establish). Implements
    :class:`~ai_os_sdk.contracts.Agent` +
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
    directly — no ``ai_os_kernel`` import anywhere.

    ``timeout_seconds``/``max_output_bytes`` are optional constructor
    overrides — always their defaults in production, and how a test
    tightens the limits."""

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        timeout_seconds: float = _SCAN_TIMEOUT_SECONDS,
        max_output_bytes: int = _SCAN_MAX_OUTPUT_BYTES,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.tools is None:
            raise SecurityAnalysisInstructionError(
                "SecurityAnalysisAgentEntrypoint.execute() called before bind_pack_context() "
                "bound a PackContext granting the sandbox:execute permission (context.tools) "
                "— a real caller must inject one before first use"
            )

        working_directory_raw, file_path_raw = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        if not await asyncio.to_thread(working_directory.is_dir):
            raise SecurityAnalysisInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        relative_path = await asyncio.to_thread(
            lambda: _resolve_existing_file(working_directory, file_path_raw).relative_to(
                working_directory.resolve()
            )
        )

        result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", _SCAN_SCRIPT, str(relative_path)],
                "working_directory": str(working_directory),
                "timeout_seconds": self._timeout_seconds,
                "max_output_bytes": self._max_output_bytes,
            },
        )

        try:
            parsed = json.loads(result.stdout) if result.stdout else {"findings": []}
        except json.JSONDecodeError as exc:
            raise SecurityAnalysisInstructionError(
                f"the scan script's own stdout was not valid JSON: {exc}\nstdout: {result.stdout}"
            ) from exc

        return {
            "passed": result.exit_code == 0,
            "exitCode": result.exit_code,
            "findings": parsed.get("findings", []),
        }
