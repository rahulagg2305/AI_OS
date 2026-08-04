"""Prefixed ULID identifiers for Context Manager objects.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids`/:mod:`ai_os_kernel.
llm_gateway.ids` exactly (data_model.md §2: "Prefixed ULID text ...
Sortable, opaque, safe in URLs and logs."). ``asm_`` is a reasoned
choice, not an invented column. Originally generated purely in-memory,
identifying one :class:`~ai_os_kernel.context_manager.models.
AssembledContext` for the duration of one request only — no persistence
table existed yet (data_model.md documented none for a context assembly
at all). **As of ``P02-S03-M08-T10``, this is also the real primary key
of a durable ``context.context_assemblies`` row** (data_model.md §9b,
:mod:`ai_os_kernel.context_manager.audit_logger`) whenever a real
:class:`~ai_os_kernel.context_manager.audit_logger.ContextAuditLogger`
is configured — the identical id, unchanged, now optionally durable.
"""

from ulid import ULID


def new_assembly_id() -> str:
    return f"asm_{ULID()}"
