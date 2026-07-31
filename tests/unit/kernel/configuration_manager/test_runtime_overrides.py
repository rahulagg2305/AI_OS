"""Unit tests for :class:`RuntimeOverrideStore` against a fake
:class:`~ai_os_kernel.configuration_manager.audit.ConfigChangeWriter` —
no database. The real, Postgres-backed audit proof lives in
``tests/integration/configuration_manager/test_runtime_overrides_audit.py``.
"""

import asyncio
from typing import Any

from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore


class _FakeConfigChangeWriter:
    """The one real seam :meth:`RuntimeOverrideStore.apply` depends on —
    satisfied structurally, no mocking framework."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None:
        self.calls.append(
            {
                "config_key": config_key,
                "old_value": old_value,
                "new_value": new_value,
                "changed_by": changed_by,
                "reason": reason,
            }
        )


def test_snapshot_is_empty_before_any_override_is_applied() -> None:
    store = RuntimeOverrideStore()
    assert store.snapshot() == {}


def test_apply_updates_the_snapshot() -> None:
    store = RuntimeOverrideStore()
    writer = _FakeConfigChangeWriter()

    asyncio.run(
        store.apply(
            writer,
            config_key="log_level",
            new_value="DEBUG",
            changed_by="user-1",
            reason="investigating an incident",
        )
    )

    assert store.snapshot() == {"log_level": "DEBUG"}


def test_apply_audits_before_the_change_is_observable() -> None:
    """Not just "audits eventually" — the recorded old_value is the
    real prior state, and a second apply's old_value reflects the
    first apply's new_value, proving the audit call is genuinely wired
    to each transition, not just a fire-and-forget side note."""
    store = RuntimeOverrideStore()
    writer = _FakeConfigChangeWriter()

    asyncio.run(
        store.apply(
            writer,
            config_key="log_level",
            new_value="DEBUG",
            changed_by="user-1",
            reason="first change",
        )
    )
    asyncio.run(
        store.apply(
            writer,
            config_key="log_level",
            new_value="ERROR",
            changed_by="user-2",
            reason="second change",
        )
    )

    assert len(writer.calls) == 2
    assert writer.calls[0]["old_value"] is None
    assert writer.calls[0]["new_value"] == "DEBUG"
    assert writer.calls[1]["old_value"] == "DEBUG"
    assert writer.calls[1]["new_value"] == "ERROR"
    assert store.snapshot() == {"log_level": "ERROR"}


def test_apply_tracks_independent_keys_independently() -> None:
    store = RuntimeOverrideStore()
    writer = _FakeConfigChangeWriter()

    asyncio.run(
        store.apply(writer, config_key="log_level", new_value="DEBUG", changed_by="u", reason="r")
    )
    asyncio.run(store.apply(writer, config_key="port", new_value=9000, changed_by="u", reason="r"))

    assert store.snapshot() == {"log_level": "DEBUG", "port": 9000}
