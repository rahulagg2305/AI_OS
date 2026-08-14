"""`MemoryService` — §6's mediated write path (`P02-S04-M10-T04`).

The store is substituted by a **real fake** (ADR-0004), not a mock: it
implements `MemoryStore` genuinely, records exactly what it was handed,
and returns a real `MemoryRecord`. Assertions are on what the service
actually produced and actually emitted — `structlog`'s own real capture
pipeline — never on "a mock was called with".
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
import structlog
from pydantic import ValidationError

from ai_os_kernel.memory_manager import (
    PROVENANCE_SCHEMA_VERSION,
    MemoryService,
    MemoryWrite,
    get_memory_writes_counter,
)
from ai_os_kernel.persistence.memory_writer import MemoryRecord, MemoryType


class _RecordingMemoryStore:
    """A real `MemoryStore`, not a mock — it honours the Protocol and
    returns a genuine `MemoryRecord` built from what it received."""

    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    async def write_memory(
        self,
        *,
        memory_type: MemoryType,
        content: str,
        source_workflow_id: str,
        quality_signal: Decimal | None = None,
        expires_at: datetime | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        self.writes.append(
            {
                "memory_type": memory_type,
                "content": content,
                "source_workflow_id": source_workflow_id,
                "quality_signal": quality_signal,
                "expires_at": expires_at,
                "provenance": provenance,
            }
        )
        return MemoryRecord(
            memory_id=f"mem_{len(self.writes):026d}",
            memory_type=memory_type,
            content=content,
            source_workflow_id=source_workflow_id,
            quality_signal=quality_signal,
            promoted_at=None,
            expires_at=expires_at,
            provenance=provenance or {},
        )

    async def query_memories(
        self,
        *,
        memory_type: MemoryType | None = None,
        source_workflow_id: str | None = None,
        limit: int,
    ) -> list[MemoryRecord]:  # pragma: no cover - MemoryService never reads
        raise AssertionError("MemoryService must not read; reads go through the Context Manager")


@pytest.mark.asyncio
async def test_write_passes_every_real_field_through_to_the_store() -> None:
    store = _RecordingMemoryStore()
    expires = datetime(2027, 1, 1, tzinfo=UTC)

    ref = await MemoryService(store).write(
        MemoryWrite(
            memory_type="engineering",
            content="the retry policy caps at 3 attempts",
            source_workflow_id="wf_01ABC",
            quality_signal=Decimal("0.75"),
            expires_at=expires,
        )
    )

    written = store.writes[0]
    assert written["memory_type"] == "engineering"
    assert written["content"] == "the retry policy caps at 3 attempts"
    assert written["source_workflow_id"] == "wf_01ABC"
    assert written["quality_signal"] == Decimal("0.75")
    assert written["expires_at"] == expires
    assert ref.memory_id == "mem_00000000000000000000000001"
    assert ref.memory_type == "engineering"


@pytest.mark.asyncio
async def test_the_returned_ref_is_narrower_than_the_stored_record() -> None:
    """§5.5 returns a *reference*, not the row. A caller that just
    supplied the content has no need to be handed it back, and the
    mediated surface should not depend on a Kernel row shape."""
    ref = await MemoryService(_RecordingMemoryStore()).write(
        MemoryWrite(memory_type="workflow", content="c", source_workflow_id="wf_1")
    )

    assert set(ref.model_dump()) == {"memory_id", "memory_type"}


@pytest.mark.asyncio
async def test_a_real_write_emits_the_observability_event_section_8_requires() -> None:
    """§8 requires every significant memory operation to record what
    was written, its source workflow and real identifiers. Nothing
    emitted anything before this service existed."""
    with structlog.testing.capture_logs() as logs:
        await MemoryService(_RecordingMemoryStore()).write(
            MemoryWrite(
                memory_type="engineering",
                content="a lesson worth keeping",
                source_workflow_id="wf_01ABC",
                step_id="analyze",
                agent_id="se.architect",
            )
        )

    written = [entry for entry in logs if entry["event"] == "memory.written"]
    assert len(written) == 1
    event = written[0]
    assert event["memory_id"] == "mem_00000000000000000000000001"
    assert event["memory_type"] == "engineering"
    assert event["source_workflow_id"] == "wf_01ABC"
    assert event["step_id"] == "analyze"
    assert event["agent_id"] == "se.architect"
    assert event["content_length"] == len("a lesson worth keeping")
    assert event["log_level"] == "info"


@pytest.mark.asyncio
async def test_the_memory_content_itself_is_never_logged() -> None:
    """A memory body can be arbitrarily large and arbitrarily
    sensitive. §8 asks for identity and provenance, not the payload."""
    sensitive_body = "customer ACME-9931 escalated after the outage on the 14th"

    with structlog.testing.capture_logs() as logs:
        await MemoryService(_RecordingMemoryStore()).write(
            MemoryWrite(memory_type="workflow", content=sensitive_body, source_workflow_id="wf_1")
        )

    assert not any(sensitive_body in str(value) for entry in logs for value in entry.values())


@pytest.mark.asyncio
async def test_a_metrics_outage_never_fails_a_write_that_committed() -> None:
    """The row is already in the database by the time telemetry runs.
    Raising here would turn a monitoring problem into a data-loss one."""
    import ai_os_kernel.memory_manager.service as service_module

    class _ExplodingCounter:
        def add(self, amount: int, attributes: dict[str, object]) -> None:
            raise RuntimeError("metric backend is down")

    store = _RecordingMemoryStore()
    original = service_module._memory_writes_counter
    service_module._memory_writes_counter = _ExplodingCounter()  # type: ignore[assignment]
    try:
        with structlog.testing.capture_logs() as logs:
            ref = await MemoryService(store).write(
                MemoryWrite(memory_type="workflow", content="c", source_workflow_id="wf_1")
            )
    finally:
        service_module._memory_writes_counter = original

    assert ref.memory_id == "mem_00000000000000000000000001"
    assert len(store.writes) == 1
    events = [entry["event"] for entry in logs]
    assert "memory.metric_failed" in events
    assert "memory.written" in events


def test_the_counter_is_created_once_and_reused() -> None:
    """Instruments are created a single time and reused — the same
    contract `get_http_requests_counter` documents."""
    assert get_memory_writes_counter() is get_memory_writes_counter()


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_content_is_refused_at_the_boundary(blank: str) -> None:
    with pytest.raises(ValidationError):
        MemoryWrite(memory_type="workflow", content=blank, source_workflow_id="wf_1")


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_source_workflow_id_is_refused_at_the_boundary(blank: str) -> None:
    with pytest.raises(ValidationError):
        MemoryWrite(memory_type="workflow", content="c", source_workflow_id=blank)


@pytest.mark.asyncio
async def test_malformed_input_never_reaches_the_store() -> None:
    """Rejecting at the boundary is the point of a mediated path: the
    store — and Postgres behind it — is never touched at all."""
    store = _RecordingMemoryStore()
    with pytest.raises(ValidationError):
        MemoryWrite(memory_type="workflow", content="  ", source_workflow_id="wf_1")

    assert store.writes == []


def test_a_caller_cannot_ask_for_an_already_promoted_memory() -> None:
    """§5.5: promotion "is a platform decision, not a pack decision".
    Pydantic's default would silently *ignore* this field, which looks
    exactly like enforcement until someone relies on it — `extra=forbid`
    makes the attempt a real error instead."""
    with pytest.raises(ValidationError):
        MemoryWrite(
            memory_type="engineering",
            content="c",
            source_workflow_id="wf_1",
            promoted_at=datetime(2026, 1, 1, tzinfo=UTC),  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_provenance_is_composed_by_the_platform_not_supplied() -> None:
    """`P02-S04-M10-T05`: the column used to be write-through, so a
    caller could assert anything. Asserted on what the store genuinely
    received, which is the value that actually lands in Postgres."""
    store = _RecordingMemoryStore()
    before = datetime.now(UTC)

    await MemoryService(store).write(
        MemoryWrite(
            memory_type="engineering",
            content="prefer perf_counter for elapsed time",
            source_workflow_id="wf_01ABC",
            step_id="analyze",
            agent_id="se.architect",
        )
    )

    provenance = store.writes[0]["provenance"]
    assert provenance["schemaVersion"] == PROVENANCE_SCHEMA_VERSION
    assert provenance["workflowId"] == "wf_01ABC"
    assert provenance["stepId"] == "analyze"
    assert provenance["agentId"] == "se.architect"
    assert provenance["trust"] == "untrusted"
    assert provenance["recordedBy"] == "ai_os_kernel.memory_manager.MemoryService"

    recorded_at = datetime.fromisoformat(provenance["recordedAt"])
    assert before <= recorded_at <= datetime.now(UTC)


def test_a_caller_cannot_assert_its_own_provenance() -> None:
    """The whole point of `P02-S04-M10-T05`. `extra="forbid"` means an
    attempt is a loud error, not a silently ignored one — the identical
    reasoning the Project Intelligence pack's `DERIVED_CONTENT_TRUST`
    states: a parameter would let a caller misrepresent provenance."""
    with pytest.raises(ValidationError):
        MemoryWrite(
            memory_type="engineering",
            content="c",
            source_workflow_id="wf_1",
            provenance={"trust": "trusted"},  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_memory_provenance_is_always_untrusted() -> None:
    """ADR-0016 control 1, and what `MemoryResolver` already asserts for
    every memory item. Not reachable as a parameter at all, so this
    holds for every write rather than by convention."""
    store = _RecordingMemoryStore()

    for memory_type in ("workflow", "engineering", "asset"):
        await MemoryService(store).write(
            MemoryWrite(
                memory_type=memory_type,
                content="c",
                source_workflow_id="wf_1",
            )
        )

    assert [write["provenance"]["trust"] for write in store.writes] == [
        "untrusted",
        "untrusted",
        "untrusted",
    ]


@pytest.mark.asyncio
async def test_an_absent_step_and_agent_are_recorded_honestly_as_null() -> None:
    """A write outside any step is a real case. Recording `None` is
    honest; a fabricated placeholder would not be."""
    store = _RecordingMemoryStore()

    await MemoryService(store).write(
        MemoryWrite(memory_type="workflow", content="c", source_workflow_id="wf_1")
    )

    provenance = store.writes[0]["provenance"]
    assert provenance["stepId"] is None
    assert provenance["agentId"] is None
    assert provenance["workflowId"] == "wf_1"


def test_a_caller_cannot_choose_the_memory_id() -> None:
    """Identity is the platform's to assign, the same reasoning as
    `promoted_at` — `SqlMemoryStore` mints a real prefixed ULID."""
    with pytest.raises(ValidationError):
        MemoryWrite(
            memory_type="workflow",
            content="c",
            source_workflow_id="wf_1",
            memory_id="mem_chosen_by_caller",  # type: ignore[call-arg]
        )
