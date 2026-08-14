"""Memory Manager — experiential knowledge: what happened, what worked.

Workflow memory (run-scoped) and engineering memory (promoted,
long-lived). Never overrides authoritative Knowledge. Promotion,
decay, and archival are deferred until real usage data exists to
calibrate them (see docs/03_architecture/kernel/memory_manager.md §6.1).

See docs/03_architecture/kernel/memory_manager.md.

Implemented so far:

- A real Memory store (:mod:`ai_os_kernel.persistence.memory_writer`,
  ``P02-S04-M10-T01``) — write and structurally-filtered query for
  ``knowledge.memory_items``, placed in ``persistence/`` rather than
  this package, the identical "no owning domain component yet"
  reasoning :mod:`ai_os_kernel.persistence.knowledge_writer` already
  established. It stays there: this package now owns the *mediated*
  concern, not the persistence boundary beneath it.
- Since ``P02-S04-M10-T04``, this package's own first real code:
  :class:`~ai_os_kernel.memory_manager.service.MemoryService`, §6's
  only mediated write path, with §8's observability requirements
  finally given a producer. See that module's docstring for why it is
  Kernel-local rather than an SDK Protocol (a decided deferral,
  ``platform_sdk_v1_scope.md`` §7), why it has no ``recall()``, and why
  it deliberately has no production caller yet.

- Since ``P02-S04-M10-T05``, ``knowledge.memory_items.provenance`` is
  **computed by the platform rather than asserted by the caller**.
  ``MemoryWrite`` has no ``provenance`` field at all; the service
  composes the record from a FK-verified workflow, a platform clock,
  its own identity, and a constant ADR-0016 trust level. See
  ``service._compose_provenance`` for which fields are genuinely
  verified and which are only declared.

Promotion, decay, and archival remain deferred (§6.1).
"""

from ai_os_kernel.memory_manager.service import (
    PROVENANCE_SCHEMA_VERSION,
    MemoryRef,
    MemoryService,
    MemoryWrite,
    get_memory_writes_counter,
)

__all__ = [
    "PROVENANCE_SCHEMA_VERSION",
    "MemoryRef",
    "MemoryService",
    "MemoryWrite",
    "get_memory_writes_counter",
]
