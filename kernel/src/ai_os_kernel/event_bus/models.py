"""Event Bus event contract.

event_bus.md §5 Event Contract: every event carries ``event_id``,
``event_type``, ``timestamp``, ``source``, an optional ``trace_id``/
``workflow_id`` (when applicable), a structured ``payload``, and
``schema_version``. §9 settles schema management as "not open": typed,
versioned Pydantic v2 event models, ``schema_version`` on every event —
not a bare dict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_os_kernel.event_bus.ids import new_event_id


class Event(BaseModel):
    """One typed, versioned event carried by the bus."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=new_event_id)
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
    trace_id: str | None = None
    workflow_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
