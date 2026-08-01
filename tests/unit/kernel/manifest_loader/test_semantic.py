"""Semantic manifest validation (``P01-S03-M02-T04``) — rule 13 (SDK
version range) and rule 16 (workflow-definition existence + step-
reference resolution). Rule 20 (workflow/sub-workflow circularity) is
deliberately not covered here — see ``semantic.py``'s own docstring for
why it is currently unenforceable, not merely unbuilt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.manifest_loader import ManifestError
from ai_os_kernel.manifest_loader.semantic import (
    validate_sdk_version_range,
    validate_workflow_definitions,
)

_RUNNING_SDK_VERSION = "0.1.0"  # ai-os-sdk's own real, installed version


def _manifest(*, sdk_version: str) -> dict[str, Any]:
    return {
        "metadata": {"id": "example-pack"},
        "dependencies": {"sdkVersion": sdk_version},
    }


# --- Rule 13: SDK version range -------------------------------------


def test_a_satisfied_range_passes() -> None:
    validate_sdk_version_range(_manifest(sdk_version=">=0.1.0,<1.0.0"))  # must not raise


def test_an_exact_pin_matching_the_running_version_passes() -> None:
    validate_sdk_version_range(_manifest(sdk_version=f"=={_RUNNING_SDK_VERSION}"))


def test_an_unsatisfied_range_is_rejected() -> None:
    with pytest.raises(ManifestError, match="sdkVersion"):
        validate_sdk_version_range(_manifest(sdk_version=">=5.0.0"))


def test_an_invalid_specifier_is_rejected_clearly() -> None:
    with pytest.raises(ManifestError, match="not a valid PEP 440 range"):
        validate_sdk_version_range(_manifest(sdk_version="not-a-real-range"))


# --- Rule 16: workflow-definition existence + step-reference resolution --

_VALID_WORKFLOW_DEFINITION: dict[str, Any] = {
    "id": "example.pipeline",
    "name": "Example Pipeline",
    "description": "A fixture workflow used only by unit tests.",
    "version": "1.0.0",
    "inputs": {},
    "outputs": {},
    "failureHandling": {"onError": "halt"},
    "steps": [
        {
            "id": "step-one",
            "type": "agent",
            "agentId": "example-pack/worker",
            "promptId": "worker.instruct",
            "promptVersion": "0.1.0",
        }
    ],
}


def _pack_manifest(
    *, workflow_definition_relpath: str = "workflows/pipeline.yaml"
) -> dict[str, Any]:
    return {
        "metadata": {"id": "example-pack"},
        "agents": [{"id": "worker"}],
        "tools": [],
        "prompts": [{"id": "worker.instruct", "version": "0.1.0"}],
        "workflows": [
            {"id": "example.pipeline", "definition": workflow_definition_relpath},
        ],
    }


def _write_workflow_definition(manifest_dir: Path, relpath: str, content: dict[str, Any]) -> None:
    path = manifest_dir / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def test_a_valid_workflow_with_resolvable_references_passes(tmp_path: Path) -> None:
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", _VALID_WORKFLOW_DEFINITION)
    manifest_path = tmp_path / "manifest.yaml"

    validate_workflow_definitions(_pack_manifest(), manifest_path)  # must not raise


def test_a_manifest_with_no_workflows_is_a_clean_no_op(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    validate_workflow_definitions({"metadata": {"id": "example-pack"}}, manifest_path)


def test_a_missing_workflow_definition_file_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="not found"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_malformed_workflow_yaml_is_rejected_clearly(tmp_path: Path) -> None:
    path = tmp_path / "workflows" / "pipeline.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("not: valid: yaml: [", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="example.pipeline"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_a_structurally_invalid_workflow_definition_is_rejected(tmp_path: Path) -> None:
    invalid = {**_VALID_WORKFLOW_DEFINITION, "steps": []}  # WorkflowDefinition requires >=1
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", invalid)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="example.pipeline"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_an_unresolvable_agent_id_is_rejected(tmp_path: Path) -> None:
    step = {**_VALID_WORKFLOW_DEFINITION["steps"][0], "agentId": "example-pack/no-such-agent"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="does not resolve to any agent"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_a_cross_pack_agent_id_is_rejected(tmp_path: Path) -> None:
    step = {**_VALID_WORKFLOW_DEFINITION["steps"][0], "agentId": "some-other-pack/worker"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="cross-pack"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_an_agent_id_without_the_pack_prefix_form_is_rejected(tmp_path: Path) -> None:
    step = {**_VALID_WORKFLOW_DEFINITION["steps"][0], "agentId": "worker"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="not in '<pack-id>/<agent-id>' form"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_an_unresolvable_prompt_id_is_rejected(tmp_path: Path) -> None:
    step = {**_VALID_WORKFLOW_DEFINITION["steps"][0], "promptId": "no.such.prompt"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="does not resolve to any prompt"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_a_prompt_id_with_the_wrong_version_is_rejected(tmp_path: Path) -> None:
    step = {**_VALID_WORKFLOW_DEFINITION["steps"][0], "promptVersion": "9.9.9"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="does not resolve to any prompt"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_an_unresolvable_tool_id_is_rejected(tmp_path: Path) -> None:
    step = {
        "id": "tool-step",
        "type": "tool",
        "toolId": "no.such.tool",
    }
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="does not resolve to any tool"):
        validate_workflow_definitions(_pack_manifest(), manifest_path)


def test_a_resolvable_tool_id_passes(tmp_path: Path) -> None:
    step = {"id": "tool-step", "type": "tool", "toolId": "example.tool"}
    definition = {**_VALID_WORKFLOW_DEFINITION, "steps": [step]}
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", definition)
    manifest = _pack_manifest()
    manifest["tools"] = [{"id": "example.tool"}]
    manifest_path = tmp_path / "manifest.yaml"

    validate_workflow_definitions(manifest, manifest_path)  # must not raise


def test_multiple_workflows_are_each_validated(tmp_path: Path) -> None:
    _write_workflow_definition(tmp_path, "workflows/pipeline.yaml", _VALID_WORKFLOW_DEFINITION)
    manifest = _pack_manifest()
    manifest["workflows"].append({"id": "example.second", "definition": "workflows/missing.yaml"})
    manifest_path = tmp_path / "manifest.yaml"

    with pytest.raises(ManifestError, match="example.second"):
        validate_workflow_definitions(manifest, manifest_path)
