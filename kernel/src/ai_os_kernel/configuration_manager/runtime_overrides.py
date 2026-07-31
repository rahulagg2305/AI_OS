"""Layer 5, runtime configuration overrides (data_model.md's own
§4 in configuration_manager.md: "Runtime overrides — ``PATCH
/api/v1/config``, audited") — ``P01-S02-M01-T04``.

Unlike layers 2-4 (pure, stateless merges over already-resolved file or
manifest input), §4 requires this layer specifically to be *audited*.
:class:`RuntimeOverrideStore` keeps that concern in one place:
:meth:`RuntimeOverrideStore.apply` records a real
``governance.config_changes`` row via the already-proven
:class:`~ai_os_kernel.configuration_manager.audit.ConfigChangeWriter`
(``P01-S02-M01-T08``) *before* the override takes effect, then updates
the in-memory current value — "audited" is not a documentation note
here, it is the one thing this class cannot skip.

The store is deliberately in-memory and synchronous to read
(:meth:`snapshot`): :meth:`~ai_os_kernel.configuration_manager.loader.
ConfigurationManager.load` merges a snapshot, never awaits anything, so
resolving configuration never depends on the database being reachable.
Only *applying* a new override is async (it must write the audit row).
Building the ``PATCH /api/v1/config`` route that would call
:meth:`apply` is separate, later work — this class is the layer that
route calls into, not the route itself.
"""

from __future__ import annotations

import threading
from typing import Any

from ai_os_kernel.configuration_manager.audit import ConfigChangeWriter


class RuntimeOverrideStore:
    """The current, in-memory set of runtime overrides — layer 5's live
    state for one process. Thread-safe: a future HTTP handler calling
    :meth:`apply` and :meth:`ConfigurationManager.load` reading
    :meth:`snapshot` may run concurrently."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        """Every currently-applied override, for
        :meth:`~ai_os_kernel.configuration_manager.loader.
        ConfigurationManager.load` to merge in above every file layer."""
        with self._lock:
            return dict(self._values)

    async def apply(
        self,
        writer: ConfigChangeWriter,
        *,
        config_key: str,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None:
        """The real "override request" this Task's Input names: audits
        the change first, then applies it, so nothing can observe an
        override through :meth:`snapshot` without a corresponding
        ``governance.config_changes`` row already existing for it."""
        with self._lock:
            old_value = self._values.get(config_key)
        await writer.record(
            config_key=config_key,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            reason=reason,
        )
        with self._lock:
            self._values[config_key] = new_value
