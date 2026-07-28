"""The Workflow Event Record — the in-memory shape of one row of
``workflow.workflow_events`` (data_model.md §4.2): the append-only log,
as opposed to :class:`ai_os_kernel.workflow_engine.instance.WorkflowInstance`
(the materialised snapshot) or
:class:`ai_os_kernel.workflow_engine.step_record.WorkflowStepRecord`
(materialised per-step state).

This is a read model returned by a query, not a new architectural
concept: every field here already exists as a column created by the
Stage B persistence-foundation migration
(``kernel/alembic/versions/0001_workflow_state_baseline.py``) and
written by every event-appending method in
:mod:`ai_os_kernel.workflow_engine.repository`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowEventRecord(BaseModel):
    """One ``workflow_events`` row.

    ``event_type`` is a plain ``str``, not an enum: data_model.md §4.2
    lists example values (``workflow.started``, ``step.started``, …)
    ending in an ellipsis — an explicitly open-ended, illustrative set,
    not a closed list like ``step_type``'s seven values. Enumerating
    one here would invent a closed vocabulary the doc deliberately
    does not declare, and the table itself has no ``CHECK`` constraint
    on this column either.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    workflow_id: str
    seq: int
    event_type: str
    schema_version: int
    payload: dict[str, Any]
    trace_id: str | None
    step_id: str | None
    agent_id: str | None
    occurred_at: datetime
