"""The `language.detect` Tool — this pack's second real increment
(`P05-S02-M32-T02`, FR-051: "Detect languages, frameworks, and build
systems in use," acceptance criterion: "Detection report produced with
confidence per finding").

**`tier2_trusted`, not `tier1_sandboxed` — a real, disclosed
classification decision, not an oversight.** `repository_ingestion.py`'s
own `repository.ingest` Tool is Tier 1 because it reads real repository
*content* from a real filesystem (ADR-0016's own unconditional rule).
This Tool never touches a filesystem, a network, or executes anything
at all — its only input is the *already-extracted* `files` list
`repository.ingest` itself already produced (a list of path/language
string pairs), and its only operation is pattern-matching well-known
basenames against that list. There is no raw file content, no
execution, and no I/O of any kind here to sandbox — the real risk
ADR-0016 Tier 1 exists to contain (malicious generated code, prompt
injection via untrusted content) has already been fully absorbed by
whichever upstream step produced `files` in the first place.

**Real, deterministic, disclosed confidence — never fabricated.**
- **Languages**: derived from `files` itself, not re-detected. The
  single language with the most files is `"high"` confidence
  (`"other"` excluded — it is an unclassified bucket, not a detected
  language). Any other language present is `"medium"` if its own share
  of classified files is at least 10%, else `"low"` — a named,
  documented heuristic (:data:`_SECONDARY_LANGUAGE_CONFIDENCE_THRESHOLD`),
  not an invented number with nothing behind it.
- **Build systems / frameworks**: detected only by the real presence of
  a well-known marker file's own basename somewhere in `files` (e.g.
  `package.json`, `pyproject.toml`, `Cargo.toml`) — always `"high"`
  confidence in this first real slice, since a marker file's presence
  is unambiguous, deterministic evidence, not a partial signal. No
  marker present means no finding reported — never a guess.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_os_sdk.models.tool import TrustTier

# Named, documented, extensible registries — not hardcoded magic
# scattered through the detection logic itself. Real, common markers
# this project's own toolchain and ecosystem knowledge already covers;
# extending either is a one-line change here, never a change to
# `execute()`.
_BUILD_SYSTEM_MARKERS: dict[str, str] = {
    "package.json": "npm/Node.js",
    "pyproject.toml": "Python (pyproject.toml)",
    "requirements.txt": "pip (requirements.txt)",
    "Cargo.toml": "Cargo (Rust)",
    "pom.xml": "Maven (Java)",
    "build.gradle": "Gradle (Java/Kotlin)",
    "build.gradle.kts": "Gradle (Java/Kotlin)",
    "go.mod": "Go modules",
    "Gemfile": "Bundler (Ruby)",
    "composer.json": "Composer (PHP)",
}

_FRAMEWORK_MARKERS: dict[str, str] = {
    "next.config.js": "Next.js",
    "next.config.ts": "Next.js",
    "angular.json": "Angular",
    "manage.py": "Django",
    "artisan": "Laravel",
}

_SECONDARY_LANGUAGE_CONFIDENCE_THRESHOLD = 0.1

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "languages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fileCount": {"type": "integer"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["name", "fileCount", "confidence"],
            },
        },
        "buildSystems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["name", "evidence", "confidence"],
            },
        },
        "frameworks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["name", "evidence", "confidence"],
            },
        },
    },
    "required": ["languages", "buildSystems", "frameworks"],
    "additionalProperties": False,
}


class LanguageDetectionToolInputError(ValueError):
    """This tool's inputs were missing the required `files` field, or
    it was not a list of `{path, language}` entries — the same
    real-input-validation contract every Tool in this project already
    enforces for its own inputs."""


def _detect_languages(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for entry in files:
        language = entry["language"]
        if language == "other":
            continue
        counts[language] = counts.get(language, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return []

    primary = max(counts.items(), key=lambda item: item[1])[0]
    results = []
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if name == primary:
            confidence = "high"
        elif count / total >= _SECONDARY_LANGUAGE_CONFIDENCE_THRESHOLD:
            confidence = "medium"
        else:
            confidence = "low"
        results.append({"name": name, "fileCount": count, "confidence": confidence})
    return results


def _detect_markers(files: list[dict[str, Any]], markers: dict[str, str]) -> list[dict[str, Any]]:
    paths_by_basename: dict[str, str] = {}
    for entry in files:
        path = entry["path"]
        basename = path.rsplit("/", 1)[-1]
        if basename in markers and basename not in paths_by_basename:
            paths_by_basename[basename] = path

    findings: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for basename, path in sorted(paths_by_basename.items()):
        name = markers[basename]
        if name in seen_names:
            continue
        seen_names.add(name)
        findings.append({"name": name, "evidence": path, "confidence": "high"})
    return sorted(findings, key=lambda finding: finding["name"])


class FileEntryInput(BaseModel):
    """One entry of this Tool's own required `files` input — the exact
    shape `repository.ingest`'s own `FileEntry` output already
    produces (see `repository_ingestion.py`)."""

    path: str
    language: str


class LanguageDetectionInput(BaseModel):
    """Documents this Tool's own manifest-declarable `inputSchema`
    reference target."""

    files: list[FileEntryInput]


class LanguageFinding(BaseModel):
    name: str
    file_count: int = Field(..., alias="fileCount")
    confidence: Literal["high", "medium", "low"]

    model_config = {"populate_by_name": True}


class MarkerFinding(BaseModel):
    name: str
    evidence: str
    confidence: Literal["high", "medium", "low"]


class LanguageDetectionOutput(BaseModel):
    """Documents this Tool's own manifest-declarable `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    languages: list[LanguageFinding]
    build_systems: list[MarkerFinding] = Field(..., alias="buildSystems")
    frameworks: list[MarkerFinding]

    model_config = {"populate_by_name": True}


class LanguageDetectionToolEntrypoint:
    """The manifest's own future `tools[].entrypoint` for
    `language.detect` — zero-argument-constructible, no injected
    collaborator of any kind needed (no sandbox, no `PackContextReceiver`):
    pure, deterministic computation over its own `inputs`."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        files = inputs.get("files")
        if not isinstance(files, list):
            raise LanguageDetectionToolInputError(
                "LanguageDetectionToolEntrypoint requires 'files' (a list of "
                "{path, language} entries, the same shape repository.ingest's own "
                "output already produces) in its inputs"
            )
        for entry in files:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("language"), str)
            ):
                raise LanguageDetectionToolInputError(
                    f"LanguageDetectionToolEntrypoint requires every 'files' entry to be "
                    f"{{'path': str, 'language': str}} — got {entry!r}"
                )

        return {
            "languages": _detect_languages(files),
            "buildSystems": _detect_markers(files, _BUILD_SYSTEM_MARKERS),
            "frameworks": _detect_markers(files, _FRAMEWORK_MARKERS),
        }
