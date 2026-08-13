"""The Workflow Instance snapshot — the in-memory shape of one row of
``workflow.workflow_instances`` (data_model.md §4.1).

This is a read model returned after a write, not a new architectural
concept: every field here already exists as a column, most created by
the Stage B persistence-foundation migration
(``kernel/alembic/versions/0001_workflow_state_baseline.py``);
``principal_permissions`` (``0031_principal_permissions``,
``P03-S05-M14-T09``) and ``scheduled_at`` (``0032_scheduled_at``,
``P02-S01-M05-T13``) are later additions.
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
    # The principal term of ADR-0023's monotonic-narrowing chain,
    # captured once at trigger time — None when no real SecurityContext
    # reached the trigger call (see ai_os_kernel.persistence.schema's
    # own column comment for why this is never an empty frozenset).
    principal_permissions: frozenset[str] | None
    # The Scheduler's own data (workflow_engine.md §5.13) — None means
    # no scheduled start was requested; a real timestamp means "start
    # no earlier than this" (P02-S01-M05-T13).
    scheduled_at: datetime | None
    # The retry epoch (`P06-S01-M36-T05`). None means this instance has
    # never been retried by an operator; a real timestamp means only
    # step failures at or after it count against the retry budget.
    retried_at: datetime | None
    last_event_seq: int
    error: dict[str, Any] | None
    total_cost_usd: Decimal
    total_tokens: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
