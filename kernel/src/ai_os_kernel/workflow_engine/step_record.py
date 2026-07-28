"""The Workflow Step Record — the in-memory shape of one row of
``workflow.workflow_steps`` (data_model.md §4.3): materialised per-step
state, as opposed to :class:`ai_os_kernel.workflow_engine.models.WorkflowStep`,
which is one step *declaration* inside a workflow definition file.

This is a read model returned by a query, not a new architectural
concept: every field here already exists as a column created by
``kernel/alembic/versions/0002_workflow_steps.py`` and written by
:meth:`ai_os_kernel.workflow_engine.repository.SqlWorkflowInstanceRepository.advance_workflow`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.workflow_engine.models import StepType


class WorkflowStepRecord(BaseModel):
    """One ``workflow_steps`` row.

    ``status`` is a plain ``str``, not an enum: unlike
    ``workflow_instances.status``, data_model.md §4.3 gives
    ``workflow_steps.status`` no canonical value list, so typing it as
    an enum here would invent one. ``step_type`` *is* typed as
    :class:`StepType` — its seven values are already documented
    (workflow_architecture.md's Supported Step Types) and already
    enforced by the table's own ``CHECK`` constraint.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str
    workflow_id: str
    step_name: str
    step_type: StepType
    status: str
    attempt: int
    agent_id: str | None
    tool_id: str | None
    prompt_id: str | None
    prompt_version: str | None
    model_alias: str | None
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    error: dict[str, Any] | None
    idempotency_key: str
    usage: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
