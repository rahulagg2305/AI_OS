"""The Notification Service's own real, minimal first increment
(`P06-S05-M22-T01`, FR-116: "Deliver approval, failure and completion
notices").

**Scoped to this ticket's own literal Goal/Input/Output, not
`notification_service.md`'s full framework document** (Notification
API, Preference Manager, Channel Router, four Channel Adapters,
Delivery Manager, retry policies): one real channel (`WebhookChannel`),
no preferences, no retries, no Dashboard/Voice/Email adapters — a
disclosed, deliberate departure from that document's own full scope,
matching this project's own established "build the real, buildable
subset" precedent (design fork resolved via `AskUserQuestion`).

**Built inside the Kernel, not as a separate `platform_services`
package** (a second design fork, same discussion): `platform_services/`
is documented as "still planned, not yet scaffolded" as its own real
`uv` workspace member, and the real `EventBus` this service must
subscribe to has no `ai-os-sdk` Protocol yet (`event_bus.md`'s own
Implementation Status) — only the Kernel-local one. Building a brand
new package that imports `ai_os_kernel.event_bus` directly would start
a new instance of the exact "pack imports Kernel internals" pattern
CLAUDE.md says not to copy in new work. This module is Kernel-internal
code depending on Kernel-internal code instead — no cross-boundary
question at all. Extracting a real `platform_services/notification`
package is real, separate, later work, once the SDK's own `EventBus`
Protocol exists or a second real consumer justifies the split.

**No real Kernel component publishes to `InProcessEventBus` in
production yet** (confirmed again while investigating this ticket —
the identical, already-disclosed gap `routes/stream.py`'s own module
docstring already names for the WebSocket endpoint). This service
subscribes for real and delivers for real; wiring a real publisher
into the Human Approval Manager or Quality Gate Engine is separate,
unbuilt work.

**Delivery status is now durably recorded** (`P06-S05-M22-T02`) —
:class:`~ai_os_kernel.notification.recorder.NotificationDeliveryRecorder`
is a required collaborator, the identical "no silent no-op default"
convention :class:`~ai_os_kernel.workflow_engine.quality_gate.
QualityGateStepExecutor`'s own required `gate_sources` already
establishes; a fake, in-memory implementation (ADR-0004) is the real
seam this service's own pure-logic unit tests substitute, since
proving *this* module correctly classifies and delivers does not need
a real database — the real recorder's own correctness is proven
separately, against real Postgres, in `test_recorder.py`.
"""

from __future__ import annotations

from typing import Protocol

from ai_os_kernel.event_bus.bus import EventBus, Subscription
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.recorder import NotificationDeliveryRecorder
from ai_os_kernel.observability.logging import get_logger

logger = get_logger(__name__)

# This service's own real, closed vocabulary — this ticket's literal
# three categories ("approval, failure and completion notices"), not
# notification_service.md's full, open-ended event surface. `approval.`
# mirrors the identical prefix convention `routes/stream.py` already
# established for the same real reason: `Event.event_type` carries no
# enum, and no real producer exists yet to have fixed one differently.
_APPROVAL_EVENT_TYPE_PREFIX = "approval."
_FAILURE_EVENT_TYPE = "workflow.failed"
_COMPLETION_EVENT_TYPE = "workflow.completed"


class DeliveryChannel(Protocol):
    """The one real channel contract this service depends on —
    `WebhookChannel` today; a future Dashboard/Voice/Email adapter
    implements the identical Protocol, not a parallel one."""

    @property
    def name(self) -> str: ...

    async def deliver(self, notification: Notification) -> bool: ...


def _notification_type_for(event: Event) -> str | None:
    """Real, closed classification — ``None`` for any event type this
    increment does not yet notify on, the same "an unrecognized input
    contributes nothing" shape this codebase already uses elsewhere
    (e.g. `WorkflowStepOutputResolver`'s own unconfigured-step case)."""
    if event.event_type.startswith(_APPROVAL_EVENT_TYPE_PREFIX):
        return "approval"
    if event.event_type == _FAILURE_EVENT_TYPE:
        return "failure"
    if event.event_type == _COMPLETION_EVENT_TYPE:
        return "completion"
    return None


class NotificationService:
    """Subscribes to the real `EventBus` for its own lifetime and
    delivers a real `Notification` for every real event matching one
    of this increment's three real categories. ``close()`` unsubscribes
    — real cleanup, the identical shape `InProcessEventBus.aclose()`
    itself already establishes for its own subscribers."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        channel: DeliveryChannel,
        recorder: NotificationDeliveryRecorder,
    ) -> None:
        self._channel = channel
        self._recorder = recorder
        self._subscription: Subscription = event_bus.subscribe(None, self._on_event)
        self._event_bus = event_bus

    async def _on_event(self, event: Event) -> None:
        notification_type = _notification_type_for(event)
        if notification_type is None:
            return

        # `status="pending"` is real and honest here — the outcome is
        # not yet known. `WebhookChannel.deliver` never sends this
        # field over the wire (the receiver has no use for the
        # sender's own not-yet-final delivery bookkeeping); the
        # recorder below persists the real, final outcome instead.
        pending = Notification(
            notification_type=notification_type,
            channel=self._channel.name,
            status="pending",
            workflow_id=event.workflow_id,
            trace_id=event.trace_id,
            payload=event.payload,
        )
        delivered = await self._channel.deliver(pending)
        final = pending.model_copy(update={"status": "sent" if delivered else "failed"})
        await self._recorder.record(final)
        logger.info(
            "notification.delivery_attempted",
            notification_type=notification_type,
            channel=self._channel.name,
            status=final.status,
            event_id=event.event_id,
        )

    def close(self) -> None:
        self._event_bus.unsubscribe(self._subscription)
