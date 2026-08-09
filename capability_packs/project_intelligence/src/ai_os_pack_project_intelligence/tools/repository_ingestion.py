"""The `repository.ingest` Tool — this pack's own first real
increment (`P05-S02-M32-T01`, FR-050: "Ingest a repository and build a
module and file inventory").

**`tier1_sandboxed`, genuinely — not a paperwork exercise.** ADR-0016's
own Decision text is unconditional: "Any tool that ... processes
untrusted repository content is Tier 1. Tier 2 is not available for
those." A repository-ingestion tool walking an arbitrary codebase is
exactly this case (ADR-0016's own Context section names "the Project
Intelligence pack ingests arbitrary codebases" as one of the two real
threats motivating that ADR in the first place). This design fork —
whether the walk itself needs to genuinely run inside a real sandbox,
versus a plain in-process directory walk — was raised and resolved via
`AskUserQuestion` (a correction mid-investigation: an earlier, incorrect
framing of this as Tier 2 was caught before any code was written).

**Mirrors `ai_os_pack_software_engineering.tools.fs_read`'s exact
shape.** `self.sandbox: Any = None` — a real `SandboxExecutor` is
injected post-construction by a real caller (the identical
`SqlToolRegistry.resolve_tool` mechanism `fs_read.py`'s own docstring
names); this pack cannot import `ai_os_kernel` at all (the same
constraint every real Tool/Agent in this codebase's other packs
already carries), so it never constructs one itself. The actual
walking/classification logic runs as a real, embedded, dependency-free
Python script (stdlib only — the sandbox's own container image
installs nothing beyond the interpreter) via `self.sandbox.execute()`,
using `self.sandbox.python_command` for backend-portability exactly as
`fs_read.py` already does.

**Real, disclosed scope:** ingests an already-checked-out local
directory (`workingDirectory`) — matching ADR-0016's own "the
workflow's isolated working copy mounted at a single writable path"
framing. Remote clone/fetch is separate, later work (most likely
already handled by an existing Git Integration Service tool before
this one ever runs). Excludes well-known non-source directories
(`.git`, `node_modules`, build/cache output, every dot-directory) by a
named, documented policy — not hardcoded, unconfigurable magic buried
inside the walk itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.models.tool import TrustTier

# A real, dependency-free, stdlib-only script — it runs inside the
# sandbox's own minimal container image, which installs nothing beyond
# the Python interpreter itself (see `docker_executor.py`'s own
# `_DEFAULT_IMAGE`). Cannot import anything from this pack's own
# `src/` tree (a separate process, a separate filesystem entirely) —
# every real value this script needs is embedded directly in its own
# source text below.
_INGEST_SCRIPT = """
import json
import os

_EXCLUDED_DIR_NAMES = {
    "node_modules", "__pycache__", "dist", "build", "vendor",
    "target", "venv", "env",
}

_LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".java": "java", ".rs": "rust", ".rb": "ruby", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".php": "php", ".sh": "shell", ".sql": "sql",
    ".md": "markdown", ".markdown": "markdown", ".txt": "plain_text",
}

# "." — not the host-side `working_directory` path: the sandbox already
# sets the container/subprocess's own current working directory to the
# real, mounted repository root (`docker_executor.py`'s own
# `_CONTAINER_WORKDIR`; `executor.py`'s own `cwd=working_directory` for
# the local backend) — the host path is meaningless *inside* a
# container's own separate filesystem.
root = "."
files = []
language_counts = {}
module_counts = {}

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [
        d for d in dirnames
        if d not in _EXCLUDED_DIR_NAMES and not d.startswith(".")
    ]
    for filename in sorted(filenames):
        full_path = os.path.join(dirpath, filename)
        rel_path = os.path.relpath(full_path, root).replace(os.sep, "/")
        extension = os.path.splitext(filename)[1].lower()
        language = _LANGUAGE_BY_EXTENSION.get(extension, "other")
        module = rel_path.split("/")[0] if "/" in rel_path else "."
        files.append({"path": rel_path, "language": language})
        language_counts[language] = language_counts.get(language, 0) + 1
        module_counts[module] = module_counts.get(module, 0) + 1

files.sort(key=lambda entry: entry["path"])
result = {
    "fileCount": len(files),
    "languageCounts": language_counts,
    "modules": [
        {"name": name, "fileCount": count}
        for name, count in sorted(module_counts.items())
    ],
    "files": files,
}
print(json.dumps(result))
"""

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fileCount": {"type": "integer"},
        "languageCounts": {"type": "object"},
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fileCount": {"type": "integer"},
                },
                "required": ["name", "fileCount"],
            },
        },
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["path", "language"],
            },
        },
    },
    "required": ["fileCount", "languageCounts", "modules", "files"],
    "additionalProperties": False,
}

_REQUIRED_INVOCATION_FIELDS = ("workingDirectory", "timeoutSeconds", "maxOutputBytes")


class RepositoryIngestionToolInputError(ValueError):
    """This tool's inputs were missing a required field, a real sandbox
    had not yet been injected, or the real sandboxed walk itself failed
    or produced output that could not be parsed as the declared
    structural model — the same real-input-validation contract every
    Tool in this project already enforces for its own inputs."""


class RepositoryIngestionInput(BaseModel):
    """Documents this Tool's own manifest-declarable `inputSchema`
    reference target — mirrors `BuildRunInput`'s own exact shape
    (`working_directory`/`timeout_seconds`/`max_output_bytes` required,
    caller-supplied, never a hardcoded default: repository sizes vary
    too widely for one fixed cap to be correct for all of them)."""

    working_directory: str = Field(..., alias="workingDirectory")
    timeout_seconds: float = Field(..., alias="timeoutSeconds")
    max_output_bytes: int = Field(..., alias="maxOutputBytes")

    model_config = {"populate_by_name": True}


class FileEntry(BaseModel):
    path: str
    language: str


class ModuleEntry(BaseModel):
    name: str
    file_count: int = Field(..., alias="fileCount")

    model_config = {"populate_by_name": True}


class RepositoryIngestionOutput(BaseModel):
    """Documents this Tool's own manifest-declarable `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    file_count: int = Field(..., alias="fileCount")
    language_counts: dict[str, int] = Field(..., alias="languageCounts")
    modules: list[ModuleEntry]
    files: list[FileEntry]

    model_config = {"populate_by_name": True}


class RepositoryIngestionToolEntrypoint:
    """The manifest's own future `tools[].entrypoint` for
    `repository.ingest` — zero-argument-constructible, no
    `PackContextReceiver` needed (only a directly-injected `sandbox`,
    the identical shape `fs_read.py`/`build_run.py` already
    establish)."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self.sandbox: Any = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        working_directory = inputs.get("workingDirectory")
        timeout_seconds = inputs.get("timeoutSeconds")
        max_output_bytes = inputs.get("maxOutputBytes")
        missing = [
            name
            for name, value in zip(
                _REQUIRED_INVOCATION_FIELDS,
                (working_directory, timeout_seconds, max_output_bytes),
                strict=True,
            )
            if value is None
        ]
        if missing:
            raise RepositoryIngestionToolInputError(
                f"RepositoryIngestionToolEntrypoint requires "
                f"{', '.join(_REQUIRED_INVOCATION_FIELDS)} in its inputs — "
                f"missing: {', '.join(missing)}"
            )
        if self.sandbox is None:
            raise RepositoryIngestionToolInputError(
                "RepositoryIngestionToolEntrypoint.execute() called before a real sandbox "
                "was injected — a real caller (SqlToolRegistry.resolve_tool) always injects "
                "one for a tier1_sandboxed tool before returning it"
            )
        assert (  # noqa: S101
            isinstance(working_directory, str)
            and isinstance(timeout_seconds, (int, float))
            and isinstance(max_output_bytes, int)
        )

        result = await self.sandbox.execute(
            command=[*self.sandbox.python_command, "-c", _INGEST_SCRIPT],
            working_directory=Path(working_directory),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        if result.timed_out:
            raise RepositoryIngestionToolInputError(
                f"RepositoryIngestionToolEntrypoint timed out walking {working_directory!r} "
                f"after {timeout_seconds}s"
            )
        if result.exit_code != 0:
            raise RepositoryIngestionToolInputError(
                f"RepositoryIngestionToolEntrypoint could not ingest {working_directory!r}: "
                f"exit code {result.exit_code}, stderr: {result.stderr.strip()}"
            )
        if result.truncated:
            raise RepositoryIngestionToolInputError(
                f"RepositoryIngestionToolEntrypoint's output for {working_directory!r} exceeded "
                f"maxOutputBytes={max_output_bytes} and was truncated — the structural model is "
                "incomplete; raise maxOutputBytes and retry rather than trust a cut-off result"
            )
        try:
            return dict(json.loads(result.stdout))
        except json.JSONDecodeError as exc:
            raise RepositoryIngestionToolInputError(
                f"RepositoryIngestionToolEntrypoint's sandboxed walk produced output that was "
                f"not valid JSON: {exc}"
            ) from exc
