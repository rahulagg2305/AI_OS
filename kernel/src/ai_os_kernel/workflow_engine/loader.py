"""Loads and validates one workflow definition file from disk.

Mirrors the two-tier clarity already established by the Manifest Loader
(:mod:`ai_os_kernel.manifest_loader`): parse, then validate, and fail
with one clear, specific error rather than a bare stack trace or a
silent partial result. Discovery/scanning across a pack's
``workflows/`` directory is not part of this step — a workflow
definition's location is already known (the pack manifest's
``workflows[].definition`` path); this loader is handed that path
directly.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from ai_os_kernel.workflow_engine.errors import WorkflowDefinitionError
from ai_os_kernel.workflow_engine.models import WorkflowDefinition


class WorkflowDefinitionLoader:
    """Loads a single workflow definition file into a validated,
    in-memory :class:`WorkflowDefinition`. Holds no state of its own —
    each call is independent; there is no registry here (out of scope
    for this step: instance creation, execution, and persistence)."""

    def load(self, definition_path: Path) -> WorkflowDefinition:
        """Load and validate ``definition_path``.

        Raises :class:`WorkflowDefinitionError` with a clear, specific
        message on any failure: missing file, invalid YAML, a
        non-mapping document, or a structural validation failure.
        """
        raw = self._parse_yaml(definition_path)
        return self._validate(raw, definition_path)

    def _parse_yaml(self, definition_path: Path) -> dict[str, object]:
        if not definition_path.is_file():
            raise WorkflowDefinitionError(f"workflow definition not found: {definition_path}")

        try:
            document = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise WorkflowDefinitionError(
                f"workflow definition '{definition_path}' is not valid YAML: {exc}"
            ) from exc

        if not isinstance(document, dict):
            raise WorkflowDefinitionError(
                f"workflow definition '{definition_path}' must be a mapping at the "
                f"top level, got {type(document).__name__}"
            )
        return document

    def _validate(self, raw: dict[str, object], definition_path: Path) -> WorkflowDefinition:
        try:
            return WorkflowDefinition.model_validate(raw)
        except ValidationError as exc:
            raise WorkflowDefinitionError(
                f"workflow definition '{definition_path}' is invalid:\n{self._format_errors(exc)}"
            ) from exc

    @staticmethod
    def _format_errors(exc: ValidationError) -> str:
        lines = []
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error["loc"]) or "<root>"
            lines.append(f"  - {location}: {error['msg']}")
        return "\n".join(lines)
