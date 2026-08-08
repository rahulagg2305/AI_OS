"""Real errors for :mod:`ai_os_kernel.notification`."""

from __future__ import annotations


class NotificationDeliveryRecordingError(Exception):
    """A ``notification.notification_deliveries`` row could not be
    recorded — wraps a persistence-layer failure with a clear message;
    the underlying exception is chained via ``from``, the identical
    shape :class:`~ai_os_kernel.workflow_engine.errors.
    GateResultRecordingError` already establishes."""
