"""`MemoryService` — §6's **only mediated write path** into memory
(`P02-S04-M10-T04`), and this package's first real code.

**What was missing.** `memory_manager/` was one 18-line docstring-only
`__init__.py` with zero classes. The real store
(:class:`~ai_os_kernel.persistence.memory_writer.SqlMemoryStore`) lives
one layer down in `persistence/`, and `MemoryResolver` (module 8) reads
it directly. `memory_manager.md` §6 names `MemoryService.write()` as the
only mediated write path and nothing implemented it, in the Kernel or
the SDK — so the package genuinely did not exist.

**Kernel-local, not an SDK Protocol — a decided question, not a guess.**
`../platform/platform_sdk.md` §5.5 specifies `MemoryService` as a
pack-facing SDK Protocol, but `platform_sdk_v1_scope.md` §7 lists it
among ten Protocols **explicitly deferred past v1.0.0**, because each
"sits on a 0%-built or docstring-only Kernel subsystem" with "no
implementation and no consumer". This module is the implementation half
that deferral was waiting on. The SDK Protocol, and the pack-facing
`PackContext.memory` attribute it would fill, remain deferred; nothing
here pre-empts their eventual shape.

**Deliberately no `recall()`.** §5.5 specifies `write()` *and*
`recall()`, but §6 and §7 both state that memory is consumed **through
the Context Manager**, never queried directly by an agent — and
`ContextManager`'s `MemoryResolver` already does exactly that, wired for
real in `bootstrap.py`. A `recall()` here would be a second read path
with no consumer, which is the "proven but idle" failure mode R-018
tracks. The read side is genuinely covered; only the write side was not.

**Not wired to a production caller, and that is a disclosed gap, not an
oversight.** Nothing writes memory in production today:
`SqlMemoryStore` appears in `bootstrap.py` twice, both times read-only
behind `MemoryResolver`. §7 says the Workflow Engine "*can* signal
important outcomes that should be written to memory" — a "can", with no
document anywhere deciding the trigger, the content, or the
`memory_type`. Inventing one would be §6.1's own named error ("a
heuristic invented before any workflows have run would be a guess
encoded as architecture"), so the trigger is left to the step that owns
it. Product-owner decision, 2026-08-14: build the service, wire nothing.

**Provenance is computed here, never accepted (`P02-S04-M10-T05`).**
`knowledge.memory_items.provenance` used to be write-through: a caller
could assert any value it liked, including none, so the column was
decorative. `MemoryWrite` no longer has a `provenance` field at all —
the service composes the record itself. See :func:`_compose_provenance`
for what is genuinely verified versus merely declared, which this
module states plainly rather than presenting as uniformly trustworthy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from opentelemetry.metrics import Counter
from pydantic import BaseModel, ConfigDict, field_validator

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.observability.metrics import configure_metrics, get_meter
from ai_os_kernel.persistence.memory_writer import MemoryStore, MemoryType

_logger = get_logger(__name__)

_MEMORY_WRITES_COUNTER_NAME = "aios.memory.writes"

# Cached for the reason `get_http_requests_counter` states outright:
# instruments are created once and reused, never re-created per call.
_memory_writes_counter: Counter | None = None


def get_memory_writes_counter() -> Counter:
    """The ``aios.memory.writes`` counter, incremented once per real,
    committed memory write.

    Configures metrics first if nothing has, so a caller reaching this
    before `configure_metrics` has run still records rather than
    crashing — the identical safety `get_http_requests_counter`
    provides.
    """
    global _memory_writes_counter
    if _memory_writes_counter is None:
        configure_metrics()
        _memory_writes_counter = get_meter(__name__).create_counter(
            _MEMORY_WRITES_COUNTER_NAME,
            unit="1",
            description="Memory items written through MemoryService.",
        )
    return _memory_writes_counter


class MemoryWrite(BaseModel):
    """One structured, mediated memory write — §5.5's own request shape.

    **This model is what "mediated" actually means here.** §6 forbids
    agents writing arbitrary memory, and the enforcement is structural
    rather than a runtime check: there is no `promoted_at` field and no
    `memory_id` field, so a caller *cannot* express "write this as
    already-promoted" or "write this under an id I chose". §5.5 states
    that promotion "is a platform decision, not a pack decision"; a
    field that does not exist cannot be set by the wrong actor.

    ``extra="forbid"`` is what makes that structural rather than
    cosmetic: Pydantic's default would *silently ignore* an attempted
    ``promoted_at=...``, which looks identical to enforcement right up
    until someone relies on it. Forbidding it turns the attempt into a
    real, loud error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_type: MemoryType
    content: str
    source_workflow_id: str
    quality_signal: Decimal | None = None
    expires_at: datetime | None = None

    # `P02-S04-M10-T05`: identity of the writer, *not* a provenance
    # assertion. There is deliberately no `provenance` field — the
    # service composes that record itself from these, so a caller can
    # no longer state its own provenance. `None` means "this write did
    # not happen inside a step / was not made by an agent", which is
    # honestly recordable; a fabricated placeholder would not be.
    step_id: str | None = None
    agent_id: str | None = None

    @field_validator("content", "source_workflow_id")
    @classmethod
    def _must_not_be_blank(cls, value: str, /) -> str:
        """Rejects blank and whitespace-only values at the boundary.

        `SqlMemoryStore` performs the identical check and keeps it —
        it is a separate boundary with its own direct callers, so this
        is defence at two real edges, not one check duplicated for its
        own sake. Rejecting here means malformed input never reaches
        Postgres at all.
        """
        if not value.strip():
            raise ValueError("must not be blank")
        return value


PROVENANCE_SCHEMA_VERSION = 1

_RECORDED_BY = "ai_os_kernel.memory_manager.MemoryService"

# ADR-0016 control 1: "Repository content, ingested documents, tool
# output, and web content are always `untrusted`". Memory content is an
# agent's own synthesized experience, which is squarely in that
# category, and `MemoryResolver` already asserts exactly this for every
# memory item it surfaces. A constant, never a parameter — the
# identical reasoning the Project Intelligence pack's own
# `DERIVED_CONTENT_TRUST` states outright: offering a parameter would
# let a caller silently misrepresent real provenance.
_MEMORY_TRUST = "untrusted"


def _compose_provenance(item: MemoryWrite, *, recorded_at: datetime) -> dict[str, Any]:
    """Build the real provenance record for one write.

    **What is genuinely verified, and what is only declared — stated
    here rather than presented as uniformly trustworthy.**

    - ``workflowId`` is *verified*: ``source_workflow_id`` is a real FK
      to ``workflow.workflow_instances``, so Postgres refuses the write
      outright if it names a workflow that does not exist. A caller
      cannot invent one.
    - ``recordedAt``, ``recordedBy``, ``trust`` and ``schemaVersion``
      are *computed*: they come from the platform clock, this module's
      own identity, and a constant. No caller can influence any of them.
    - ``stepId`` and ``agentId`` are *declared*: the writer states them
      and nothing cross-checks them today. They are recorded because
      they are the real linkage §4 asks for ("provenance and linkage to
      the originating workflow or decision") and omitting them would
      lose real information — but they are the weakest field in this
      record, and a future step that has a real `SecurityContext` at
      this call site could verify them properly.

    ``schemaVersion`` is present from the first row so a later shape
    change is a readable migration rather than an archaeology problem —
    the identical reasoning ``OUTBOX_SCHEMA_VERSION`` already applies.
    """
    return {
        "schemaVersion": PROVENANCE_SCHEMA_VERSION,
        "workflowId": item.source_workflow_id,
        "stepId": item.step_id,
        "agentId": item.agent_id,
        "trust": _MEMORY_TRUST,
        "recordedAt": recorded_at.isoformat(),
        "recordedBy": _RECORDED_BY,
    }


class MemoryRef(BaseModel):
    """§5.5's own return shape: a *reference* to what was written, not
    the whole row.

    `SqlMemoryStore.write_memory` returns a full
    :class:`~ai_os_kernel.persistence.memory_writer.MemoryRecord`, which
    is right for a persistence boundary. The mediated path deliberately
    hands back less — a caller that just wrote an item has no need to be
    handed back the content it supplied, and narrowing here keeps the
    eventual pack-facing surface from depending on a Kernel row shape.
    """

    model_config = ConfigDict(frozen=True)

    memory_id: str
    memory_type: MemoryType


class MemoryService:
    """The mediated write path §6 names, over the unchanged store.

    Takes the :class:`~ai_os_kernel.persistence.memory_writer.MemoryStore`
    Protocol rather than the concrete `SqlMemoryStore` — the ADR-0004
    substitution seam, so this service is provable against a real fake
    store without a Postgres container, while the real composition
    passes the real one.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def write(self, item: MemoryWrite) -> MemoryRef:
        """Write one memory item, and record that it happened (§8).

        §8 requires every significant memory operation to record what
        was written, its source workflow, and real identifiers. That
        requirement had no producer at all before this method: the store
        below emits nothing, and nothing above it existed.

        The telemetry is emitted **after** the store returns, so a
        failed write is never counted as a successful one, and the
        metric is guarded — a metrics outage must not fail a write that
        genuinely committed. A dropped counter is a monitoring problem;
        raising here would turn it into a data-loss one.
        """
        record = await self._store.write_memory(
            memory_type=item.memory_type,
            content=item.content,
            source_workflow_id=item.source_workflow_id,
            quality_signal=item.quality_signal,
            expires_at=item.expires_at,
            provenance=_compose_provenance(item, recorded_at=datetime.now(UTC)),
        )

        try:
            get_memory_writes_counter().add(
                1,
                {
                    "aios.memory.type": record.memory_type,
                    "aios.memory.source_workflow_id": record.source_workflow_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("memory.metric_failed", memory_id=record.memory_id, error=str(exc))

        # `content` itself is deliberately not logged — §8 asks for
        # "what was written" as identity and provenance, and a memory
        # item's body can be arbitrarily large and arbitrarily
        # sensitive. Its length is the part an operator can act on.
        #
        # `step_id`/`agent_id` are §8's own "source workflow / agent"
        # requirement. They were `has_provenance` until
        # `P02-S04-M10-T05` made provenance computed rather than
        # supplied — at which point that flag was true on every single
        # write and told an operator nothing.
        _logger.info(
            "memory.written",
            memory_id=record.memory_id,
            memory_type=record.memory_type,
            source_workflow_id=record.source_workflow_id,
            step_id=item.step_id,
            agent_id=item.agent_id,
            content_length=len(record.content),
        )

        return MemoryRef(memory_id=record.memory_id, memory_type=record.memory_type)
