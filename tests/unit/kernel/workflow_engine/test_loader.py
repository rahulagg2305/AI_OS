"""Unit tests for workflow definition loading and validation."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.workflow_engine import WorkflowDefinitionError, WorkflowDefinitionLoader

_VALID_DEFINITION: dict[str, Any] = {
    "id": "se.product_creation",
    "name": "Full Product Creation",
    "description": "Turn a structured specification into working software.",
    "version": "1.0.0",
    "inputs": {
        "type": "object",
        "properties": {"specPath": {"type": "string"}},
        "required": ["specPath"],
    },
    "outputs": {
        "type": "object",
        "properties": {"success": {"type": "boolean"}},
    },
    "steps": [
        {
            "id": "analyze_requirements",
            "type": "agent",
            "agentId": "se.software_engineering/analyst",
        },
        {"id": "build_and_test", "type": "parallel", "joinPolicy": "all"},
    ],
    "agents": ["requirements-analyst", "backend-developer"],
    "qualityGates": ["se.build"],
    "failureHandling": {"onError": "escalate"},
}


def _write_definition(path: Path, content: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def test_loads_a_valid_definition(tmp_path: Path) -> None:
    path = _write_definition(tmp_path / "product_creation.yaml", _VALID_DEFINITION)
    loader = WorkflowDefinitionLoader()

    definition = loader.load(path)

    assert definition.id == "se.product_creation"
    assert definition.version == "1.0.0"
    assert [step.id for step in definition.steps] == ["analyze_requirements", "build_and_test"]
    assert definition.steps[1].join_policy is not None
    assert definition.steps[1].join_policy.value == "all"
    assert definition.human_approval_points == []
    assert definition.retry_policy is None


def test_loads_a_definition_with_a_full_human_approval_point(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "humanApprovalPoints": [
            {
                "id": "architecture-approval",
                "name": "Architecture Approval",
                "description": "Approve the proposed architecture before implementation.",
                "context": {"documentPath": "architecture.md"},
                "options": ["approve", "reject", "request_changes"],
            }
        ],
        "retryPolicy": {"maxAttempts": 3, "maxDurationSeconds": 600},
    }
    path = _write_definition(tmp_path / "with_approval.yaml", content)
    loader = WorkflowDefinitionLoader()

    definition = loader.load(path)

    assert len(definition.human_approval_points) == 1
    assert definition.human_approval_points[0].id == "architecture-approval"
    assert definition.retry_policy is not None
    assert definition.retry_policy.max_attempts == 3


def test_missing_file_fails_clearly(tmp_path: Path) -> None:
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="not found"):
        loader.load(tmp_path / "does-not-exist.yaml")


def test_invalid_yaml_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: [unterminated", encoding="utf-8")
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="not valid YAML"):
        loader.load(path)


def test_non_mapping_document_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text(yaml.safe_dump(["not", "a", "mapping"]), encoding="utf-8")
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="must be a mapping"):
        loader.load(path)


def test_missing_required_field_fails_clearly(tmp_path: Path) -> None:
    content = {k: v for k, v in _VALID_DEFINITION.items() if k != "failureHandling"}
    path = _write_definition(tmp_path / "missing_field.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="failureHandling"):
        loader.load(path)


def test_unrecognised_field_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "notARealField": True}
    path = _write_definition(tmp_path / "extra_field.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError):
        loader.load(path)


def test_malformed_id_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "id": "Not A Valid Id"}
    path = _write_definition(tmp_path / "bad_id.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="id"):
        loader.load(path)


def test_malformed_version_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "version": "v1"}
    path = _write_definition(tmp_path / "bad_version.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="version"):
        loader.load(path)


def test_empty_steps_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "steps": []}
    path = _write_definition(tmp_path / "no_steps.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="at least one step"):
        loader.load(path)


def test_duplicate_step_ids_fail_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {"id": "same_id", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "same_id", "type": "tool", "toolId": "se.build"},
        ],
    }
    path = _write_definition(tmp_path / "duplicate_steps.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="duplicate step id"):
        loader.load(path)


def test_parallel_step_without_join_policy_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [{"id": "fan_out", "type": "parallel"}],
    }
    path = _write_definition(tmp_path / "parallel_no_policy.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="joinPolicy"):
        loader.load(path)


def test_decision_step_without_condition_or_branches_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            },
            {"id": "decide", "type": "decision"},
        ],
    }
    path = _write_definition(tmp_path / "decision_no_condition.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="condition and branches"):
        loader.load(path)


def test_decision_step_with_wrong_branch_keys_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            },
            {
                "id": "decide",
                "type": "decision",
                "condition": {
                    "sourceStepId": "analyze_requirements",
                    "field": "passed",
                    "equals": True,
                },
                "branches": {"yes": "deploy", "no": "rollback"},
            },
            {"id": "deploy", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "rollback", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
    }
    path = _write_definition(tmp_path / "decision_wrong_keys.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="exactly the keys"):
        loader.load(path)


def test_decision_step_referencing_a_forward_step_fails_clearly(tmp_path: Path) -> None:
    """A decision cannot depend on a step that has not run yet —
    rejected at load time, not discovered as a confusing runtime
    failure."""
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "decide",
                "type": "decision",
                "condition": {
                    "sourceStepId": "analyze_requirements",
                    "field": "passed",
                    "equals": True,
                },
                "branches": {"true": "deploy", "false": "rollback"},
            },
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            },
            {"id": "deploy", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "rollback", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
    }
    path = _write_definition(tmp_path / "decision_forward_ref.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="declared earlier"):
        loader.load(path)


def test_decision_step_with_an_unresolvable_branch_target_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            },
            {
                "id": "decide",
                "type": "decision",
                "condition": {
                    "sourceStepId": "analyze_requirements",
                    "field": "passed",
                    "equals": True,
                },
                "branches": {"true": "deploy", "false": "does_not_exist"},
            },
            {"id": "deploy", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
    }
    path = _write_definition(tmp_path / "decision_bad_target.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="not a declared step"):
        loader.load(path)


def test_a_well_formed_decision_step_loads_successfully(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "analyze_requirements",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
            },
            {
                "id": "decide",
                "type": "decision",
                "condition": {
                    "sourceStepId": "analyze_requirements",
                    "field": "passed",
                    "equals": True,
                },
                "branches": {"true": "deploy", "false": "rollback"},
            },
            {"id": "deploy", "type": "agent", "agentId": "se.software_engineering/analyst"},
            {"id": "rollback", "type": "agent", "agentId": "se.software_engineering/analyst"},
        ],
    }
    path = _write_definition(tmp_path / "decision_valid.yaml", content)
    loader = WorkflowDefinitionLoader()

    definition = loader.load(path)

    decide_step = next(step for step in definition.steps if step.id == "decide")
    assert decide_step.condition is not None
    assert decide_step.condition.source_step_id == "analyze_requirements"
    assert decide_step.branches == {"true": "deploy", "false": "rollback"}


def test_malformed_quality_gate_reference_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "qualityGates": ["Not A Valid Gate Id"]}
    path = _write_definition(tmp_path / "bad_gate.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="qualityGates"):
        loader.load(path)


def test_empty_failure_handling_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "failureHandling": {}}
    path = _write_definition(tmp_path / "empty_failure_handling.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="failureHandling"):
        loader.load(path)


def test_human_approval_point_without_options_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "humanApprovalPoints": [
            {
                "id": "no-options",
                "name": "No Options",
                "description": "Missing options.",
                "context": {},
                "options": [],
            }
        ],
    }
    path = _write_definition(tmp_path / "no_options.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="at least one option"):
        loader.load(path)


def test_retry_policy_without_bounds_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "retryPolicy": {"maxAttempts": 3}}
    path = _write_definition(tmp_path / "unbounded_retry.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="maxDurationSeconds"):
        loader.load(path)


def test_malformed_inputs_schema_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "inputs": {"type": "not-a-real-json-schema-type"}}
    path = _write_definition(tmp_path / "bad_inputs.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="JSON Schema"):
        loader.load(path)


def test_agent_step_without_agent_id_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "steps": [{"id": "no_agent", "type": "agent"}]}
    path = _write_definition(tmp_path / "agent_no_id.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="an agent step must declare agentId"):
        loader.load(path)


def test_tool_step_without_tool_id_fails_clearly(tmp_path: Path) -> None:
    content = {**_VALID_DEFINITION, "steps": [{"id": "no_tool", "type": "tool"}]}
    path = _write_definition(tmp_path / "tool_no_id.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="a tool step must declare toolId"):
        loader.load(path)


def test_agent_step_with_tool_id_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "agent_with_tool",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
                "toolId": "se.build",
            }
        ],
    }
    path = _write_definition(tmp_path / "agent_with_tool.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="must not declare toolId"):
        loader.load(path)


def test_tool_step_with_prompt_fields_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "tool_with_prompt",
                "type": "tool",
                "toolId": "se.build",
                "promptId": "prompt_greeting",
                "promptVersion": "1.0.0",
            }
        ],
    }
    path = _write_definition(tmp_path / "tool_with_prompt.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(
        WorkflowDefinitionError,
        match="must not declare agentId, promptId, promptVersion, or modelAlias",
    ):
        loader.load(path)


def test_human_approval_step_with_agent_id_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "approve",
                "type": "human_approval",
                "agentId": "se.software_engineering/analyst",
            }
        ],
        "humanApprovalPoints": [
            {
                "id": "approve",
                "name": "Approve",
                "description": "Approve something.",
                "context": {},
                "options": ["approve", "reject"],
            }
        ],
    }
    path = _write_definition(tmp_path / "human_approval_with_agent.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="must not declare"):
        loader.load(path)


def test_prompt_id_without_prompt_version_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "needs_version",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
                "promptId": "prompt_greeting",
            }
        ],
    }
    path = _write_definition(tmp_path / "prompt_no_version.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(
        WorkflowDefinitionError, match="promptId and promptVersion must be declared together"
    ):
        loader.load(path)


def test_prompt_version_without_prompt_id_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "needs_id",
                "type": "agent",
                "agentId": "se.software_engineering/analyst",
                "promptVersion": "1.0.0",
            }
        ],
    }
    path = _write_definition(tmp_path / "version_no_prompt.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(
        WorkflowDefinitionError, match="promptId and promptVersion must be declared together"
    ):
        loader.load(path)


def test_blank_agent_id_fails_clearly(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [{"id": "blank_agent", "type": "agent", "agentId": "   "}],
    }
    path = _write_definition(tmp_path / "blank_agent_id.yaml", content)
    loader = WorkflowDefinitionLoader()

    with pytest.raises(WorkflowDefinitionError, match="must not be blank"):
        loader.load(path)


def test_agent_step_with_full_invocation_fields_loads_successfully(tmp_path: Path) -> None:
    content = {
        **_VALID_DEFINITION,
        "steps": [
            {
                "id": "generate_code",
                "type": "agent",
                "agentId": "se.software_engineering/backend-developer",
                "promptId": "prompt_generate_code",
                "promptVersion": "1.0.0",
                "modelAlias": "fast-cheap",
            }
        ],
    }
    path = _write_definition(tmp_path / "full_invocation_fields.yaml", content)
    loader = WorkflowDefinitionLoader()

    definition = loader.load(path)

    step = definition.steps[0]
    assert step.agent_id == "se.software_engineering/backend-developer"
    assert step.prompt_id == "prompt_generate_code"
    assert step.prompt_version == "1.0.0"
    assert step.model_alias == "fast-cheap"
