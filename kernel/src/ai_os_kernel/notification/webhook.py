"""A real webhook delivery channel — POSTs the notification's own real
JSON body to a configurable URL. The one real, generic channel this
increment builds (notification_service.md §4's own "Webhook / external
system callbacks" entry) — see :mod:`ai_os_kernel.notification.service`'s
own docstring for why Dashboard/Voice/Email are deferred.
"""

from __future__ import annotations

import httpx

from ai_os_kernel.notification.models import Notification
from ai_os_kernel.observability.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 5.0


class WebhookChannel:
    """Delivers by real HTTP POST. A delivery failure (the target
    unreachable, timing out, or answering non-2xx) is a genuine,
    expected real-world condition — never raised, always returned as
    ``False`` — the identical "record the failure, do not crash the
    caller" principle every other real channel/gate in this codebase
    already establishes."""

    def __init__(
        self, *, webhook_url: str, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        if not webhook_url.strip():
            raise ValueError("webhook_url must not be blank")
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "webhook"

    async def deliver(self, notification: Notification) -> bool:
        # `status` is excluded: it is the sender's own not-yet-final
        # delivery bookkeeping (`NotificationService._on_event`'s own
        # docstring), never information the receiver has a use for.
        body = notification.model_dump(mode="json", exclude={"status"})
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._webhook_url, json=body)
            if not response.is_success:
                logger.warning(
                    "notification.webhook_delivery_failed",
                    status_code=response.status_code,
                    notification_type=notification.notification_type,
                )
            return response.is_success
        except httpx.HTTPError as exc:
            logger.warning(
                "notification.webhook_delivery_failed",
                error=str(exc),
                notification_type=notification.notification_type,
            )
            return False
