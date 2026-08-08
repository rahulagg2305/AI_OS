"""Prefixed ULID identifiers for this module's own rows — the identical
convention :mod:`ai_os_kernel.workflow_engine.ids` already establishes
(data_model.md §2: "Prefixed ULID text ... Sortable, opaque, safe in
URLs and logs.").
"""

from ulid import ULID


def new_notification_delivery_id() -> str:
    return f"ndel_{ULID()}"
