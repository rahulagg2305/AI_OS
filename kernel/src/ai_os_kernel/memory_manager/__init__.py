"""Memory Manager — experiential knowledge: what happened, what worked.

Workflow memory (run-scoped) and engineering memory (promoted,
long-lived). Never overrides authoritative Knowledge. Promotion,
decay, and archival are deferred until real usage data exists to
calibrate them (see docs/03_architecture/kernel/memory_manager.md §6.1).

See docs/03_architecture/kernel/memory_manager.md.

Implemented so far: a real Memory store
(:mod:`ai_os_kernel.persistence.memory_writer`, ``P02-S04-M10-T01``) —
write and structurally-filtered query for ``knowledge.memory_items``,
placed in ``persistence/`` rather than this package, the identical
"no owning domain component yet" reasoning
:mod:`ai_os_kernel.persistence.knowledge_writer` already established.
Promotion, decay, and archival remain deferred (§6.1) — this package
itself is still an untouched stub.
"""
