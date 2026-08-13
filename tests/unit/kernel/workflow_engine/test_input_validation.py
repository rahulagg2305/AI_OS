"""Unit tests for input validation ahead of workflow instance creation."""

from typing import Any

import pytest

from ai_os_kernel.workflow_engine import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.input_validation import validate_inputs, validate_principal
from ai_os_kernel.workflow_engine.models import WorkflowDefinition

_DEFINITION_RAW: dict[str, Any] = {
    "id": "se.product_creation",
    "name": "Full Product Creation",
    "description": "Turn a structured specification into working software.",
    "version": "1.0.0",
    "inputs": {
        "type": "object",
        "properties": {"specPath": {"type": "string"}},
        "required": ["specPath"],
    },
    "outputs": {"type": "object"},
    "steps": [
        {
            "id": "analyze_requirements",
            "type": "agent",
            "agentId": "se.software_engineering/analyst",
        }
    ],
    "failureHandling": {"onError": "halt"},
}

_DEFINITION = WorkflowDefinition.model_validate(_DEFINITION_RAW)


def test_valid_inputs_pass() -> None:
    validate_inputs(_DEFINITION, {"specPath": "specs/product.md"})


def test_inputs_violating_the_schema_fail_clearly() -> None:
    with pytest.raises(WorkflowInputValidationError, match="specPath"):
        validate_inputs(_DEFINITION, {})


def test_inputs_with_wrong_type_fail_clearly() -> None:
    with pytest.raises(WorkflowInputValidationError, match="se.product_creation"):
        validate_inputs(_DEFINITION, {"specPath": 12345})


def test_blank_principal_fails_clearly() -> None:
    with pytest.raises(WorkflowInputValidationError, match="principal_id"):
        validate_principal("")


def test_whitespace_only_principal_fails_clearly() -> None:
    with pytest.raises(WorkflowInputValidationError, match="principal_id"):
        validate_principal("   ")


def test_non_blank_principal_passes() -> None:
    validate_principal("user-42")
