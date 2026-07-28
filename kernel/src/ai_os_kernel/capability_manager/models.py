"""The Pack Record — the in-memory shape of one row of ``catalog.packs``
(data_model.md §5).

This is a read model returned after a write, not a new architectural
concept: every field here already exists as a column created by the
``catalog.packs`` migration (``0018_catalog_packs``), mirroring
:class:`~ai_os_kernel.workflow_engine.instance.WorkflowInstance`'s own
"snapshot returned immediately after a write" role.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.workflow_engine.pack_state import PackState


class PackRecord(BaseModel):
    """One ``catalog.packs`` row, as read back immediately after a
    register/activate/deactivate call, or by a plain lookup."""

    model_config = ConfigDict(frozen=True)

    pack_id: str
    version: str
    state: PackState
    manifest: dict[str, Any]
    sdk_version: str
    min_kernel_version: str
    installed_at: datetime | None
    activated_at: datetime | None
    health: dict[str, Any] | None
