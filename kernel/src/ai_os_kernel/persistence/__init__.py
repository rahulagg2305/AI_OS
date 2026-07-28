"""Workflow-state persistence: engine, Core table definitions, migrations.

Schema and connectivity only at this stage (Stage B, persistence-foundation
step). No repository classes and no Workflow Engine logic live here yet —
see docs/08_database/data_model.md §4 and ADR-0011.
"""

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import (
    metadata,
    workflow_events,
    workflow_instances,
    workflow_leases,
)
from ai_os_kernel.persistence.settings import DatabaseSettings

__all__ = [
    "DatabaseSettings",
    "build_engine",
    "metadata",
    "workflow_events",
    "workflow_instances",
    "workflow_leases",
]
