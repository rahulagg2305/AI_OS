"""The Workflow Instance snapshot — the in-memory shape of one row of
``workflow.workflow_instances`` (data_model.md §4.1).

This is a read model returned after a write, not a new architectural
concept: every field here already exists as a column created by the
Stage B persistence-foundation migration
(``kernel/alembic/versions/0001_workflow_state_baseline.py``).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowInstanceStatus(StrEnum):
    """The canonical nine-state list (workflow_engine.md §7)."""

    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    WAITING_FOR_RETRY = "waiting_for_retry"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowInstance(BaseModel):
    """One ``workflow_instances`` row, as read back immediately after
    creation."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    definition_id: str
    definition_version: str
    status: WorkflowInstanceStatus
    current_step_id: str | None
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    experiment_id: str | None
    run_manifest_id: str | None
    principal_id: str
    last_event_seq: int
    error: dict[str, Any] | None
    total_cost_usd: Decimal
    total_tokens: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
