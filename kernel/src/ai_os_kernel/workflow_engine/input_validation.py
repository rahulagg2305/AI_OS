"""Validates candidate workflow inputs against a definition's declared
``inputs`` JSON Schema before a workflow instance is created.

The definition's ``inputs`` schema was already checked for being a
*well-formed* JSON Schema document at definition-load time
(:mod:`ai_os_kernel.workflow_engine.models`). This module performs the
complementary check: does a specific candidate ``inputs`` value
*conform* to that schema.
"""

from typing import Any

from jsonschema import Draft202012Validator

from ai_os_kernel.workflow_engine.errors import WorkflowInputValidationError
from ai_os_kernel.workflow_engine.models import WorkflowDefinition


def validate_inputs(definition: WorkflowDefinition, inputs: dict[str, Any]) -> None:
    """Raise :class:`WorkflowInputValidationError` with every violation
    listed, clearly, if ``inputs`` does not satisfy
    ``definition.inputs``."""
    validator = Draft202012Validator(definition.inputs)
    errors = sorted(validator.iter_errors(inputs), key=lambda e: list(map(str, e.path)))
    if errors:
        lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
        raise WorkflowInputValidationError(
            f"inputs for workflow '{definition.id}' do not satisfy its inputs schema:\n"
            + "\n".join(lines)
        )


def validate_principal(principal_id: str) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``principal_id`` is
    blank. ``workflow_instances.principal_id`` is ``NOT NULL`` — "who
    started it" (data_model.md §4.1) — and an empty string satisfies
    that constraint while meaning nothing."""
    _require_non_blank("principal_id", principal_id)


def validate_pack_id(pack_id: str) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``pack_id`` is
    blank. ``catalog.workflow_definitions.pack_id`` is ``NOT NULL``
    (data_model.md §5) and an empty string would satisfy that constraint
    while identifying no pack."""
    _require_non_blank("pack_id", pack_id)


def validate_reason(reason: str) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``reason`` is
    blank. Every state transition's event must carry a reason
    (workflow_engine.md §7: "carrying the previous state, the new
    state, the reason, and the triggering event")."""
    _require_non_blank("reason", reason)


def validate_worker_id(worker_id: str) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``worker_id`` is
    blank. ``workflow_leases.worker_id`` is ``NOT NULL`` (data_model.md
    §4.4) and an empty string would satisfy that constraint while
    identifying no one."""
    _require_non_blank("worker_id", worker_id)


def validate_lease_duration(lease_duration_seconds: int) -> None:
    """Raise :class:`WorkflowInputValidationError` if
    ``lease_duration_seconds`` is not positive — a lease that expires
    at or before the moment it is acquired protects nothing."""
    if lease_duration_seconds <= 0:
        raise WorkflowInputValidationError("lease_duration_seconds must be positive")


def validate_max_iterations(max_iterations: int) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``max_iterations``
    is not positive — a bound of zero or fewer would never even attempt
    a single ``advance()`` call, which is never the caller's intent."""
    if max_iterations <= 0:
        raise WorkflowInputValidationError("max_iterations must be positive")


def validate_reap_limit(limit: int) -> None:
    """Raise :class:`WorkflowInputValidationError` if ``limit`` is not
    positive — a reaper pass bounded at zero or fewer would never
    examine a single lease, which is never the caller's intent."""
    if limit <= 0:
        raise WorkflowInputValidationError("limit must be positive")


def _require_non_blank(field_name: str, value: str) -> None:
    if not value or not value.strip():
        raise WorkflowInputValidationError(f"{field_name} must not be blank")
