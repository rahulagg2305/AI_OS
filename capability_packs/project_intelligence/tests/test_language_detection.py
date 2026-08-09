"""Real, deterministic tests for the `language.detect` Tool — pure
computation over already-known data, no sandbox/fake needed at all
(ADR-0004/ADR-0015 don't even apply: there is no I/O or
non-determinism here worth substituting)."""

from __future__ import annotations

import pytest

from ai_os_pack_project_intelligence.tools.language_detection import (
    LanguageDetectionInput,
    LanguageDetectionOutput,
    LanguageDetectionToolEntrypoint,
    LanguageDetectionToolInputError,
)


def _entry(path: str, language: str) -> dict[str, str]:
    return {"path": path, "language": language}


def test_entrypoint_is_tier2_trusted_not_tier1_sandboxed() -> None:
    tool = LanguageDetectionToolEntrypoint()

    assert tool.trust_tier.value == "tier2_trusted"


@pytest.mark.asyncio
async def test_missing_files_field_raises_a_clear_error() -> None:
    tool = LanguageDetectionToolEntrypoint()

    with pytest.raises(LanguageDetectionToolInputError, match="requires 'files'"):
        await tool.execute({})


@pytest.mark.asyncio
async def test_a_malformed_files_entry_raises_a_clear_error() -> None:
    tool = LanguageDetectionToolEntrypoint()

    with pytest.raises(LanguageDetectionToolInputError, match="requires every 'files' entry"):
        await tool.execute({"files": [{"path": "a.py"}]})


@pytest.mark.asyncio
async def test_the_dominant_language_is_reported_with_high_confidence() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry(f"src/mod{i}.py", "python") for i in range(9)] + [
        _entry("README.md", "markdown")
    ]

    outputs = await tool.execute({"files": files})

    LanguageDetectionOutput.model_validate(outputs)
    languages = {entry["name"]: entry for entry in outputs["languages"]}
    assert languages["python"]["confidence"] == "high"
    assert languages["python"]["fileCount"] == 9
    # markdown is 1/10 = exactly the 10% threshold -> medium, not low.
    assert languages["markdown"]["confidence"] == "medium"


@pytest.mark.asyncio
async def test_a_rare_secondary_language_is_reported_with_low_confidence() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry(f"src/mod{i}.py", "python") for i in range(20)] + [
        _entry("scripts/one_off.sh", "shell")
    ]

    outputs = await tool.execute({"files": files})

    languages = {entry["name"]: entry for entry in outputs["languages"]}
    assert languages["shell"]["confidence"] == "low"


@pytest.mark.asyncio
async def test_other_is_never_reported_as_a_detected_language() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry("a.py", "python"), _entry("data.bin", "other")]

    outputs = await tool.execute({"files": files})

    names = {entry["name"] for entry in outputs["languages"]}
    assert "other" not in names


@pytest.mark.asyncio
async def test_no_classified_files_produces_an_empty_language_list() -> None:
    tool = LanguageDetectionToolEntrypoint()

    outputs = await tool.execute({"files": [_entry("data.bin", "other")]})

    assert outputs["languages"] == []


@pytest.mark.asyncio
async def test_a_real_build_system_marker_is_detected_with_evidence() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry("package.json", "other"), _entry("src/index.js", "javascript")]

    outputs = await tool.execute({"files": files})

    assert outputs["buildSystems"] == [
        {"name": "npm/Node.js", "evidence": "package.json", "confidence": "high"}
    ]


@pytest.mark.asyncio
async def test_a_real_framework_marker_is_detected_with_evidence() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry("manage.py", "python"), _entry("app/views.py", "python")]

    outputs = await tool.execute({"files": files})

    assert outputs["frameworks"] == [
        {"name": "Django", "evidence": "manage.py", "confidence": "high"}
    ]


@pytest.mark.asyncio
async def test_a_marker_in_a_subdirectory_is_still_detected() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry("packages/api/package.json", "other")]

    outputs = await tool.execute({"files": files})

    assert outputs["buildSystems"] == [
        {"name": "npm/Node.js", "evidence": "packages/api/package.json", "confidence": "high"}
    ]


@pytest.mark.asyncio
async def test_no_marker_present_means_no_finding_never_a_guess() -> None:
    tool = LanguageDetectionToolEntrypoint()
    files = [_entry("README.md", "markdown")]

    outputs = await tool.execute({"files": files})

    assert outputs["buildSystems"] == []
    assert outputs["frameworks"] == []


def test_input_and_output_models_document_the_tool_contract() -> None:
    LanguageDetectionInput(files=[{"path": "a.py", "language": "python"}])
    LanguageDetectionOutput(
        languages=[{"name": "python", "fileCount": 1, "confidence": "high"}],
        build_systems=[],
        frameworks=[],
    )
