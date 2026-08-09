"""The Notification Contract (`notification_service.md` §8's own
documented observability fields: type, channel, delivery status,
correlation IDs, timestamp) — a real, typed record of one delivery
attempt, not a bare dict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Notification(BaseModel):
    """One real notification delivery attempt.

    ``notification_type`` is one of this service's own real, closed
    categories (``approval``/``failure``/``completion``, plus
    ``cost_anomaly`` added by ``P07-S03-M42-T02`` — still not the
    framework document's full, open-ended vocabulary). ``status`` is
    the real outcome of the one
    delivery attempt this increment makes — no retry exists yet (see
    :mod:`ai_os_kernel.notification.service`'s own docstring).
    """

    model_config = ConfigDict(frozen=True)

    notification_type: str
    channel: str
    status: str
    workflow_id: str | None
    trace_id: str | None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
