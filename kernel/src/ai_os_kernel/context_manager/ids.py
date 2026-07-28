"""Prefixed ULID identifiers for Context Manager objects.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids`/:mod:`ai_os_kernel.
llm_gateway.ids` exactly (data_model.md §2: "Prefixed ULID text ...
Sortable, opaque, safe in URLs and logs."). ``asm_`` is a reasoned
choice, not an invented column — data_model.md documents no persistence
table for a context assembly at all yet (see
:mod:`ai_os_kernel.context_manager`'s own docstring: the Context Audit
Logger context_manager.md §4 describes has no schema to write to, so
``assembly_id`` identifies one in-memory :class:`~ai_os_kernel.
context_manager.models.AssembledContext` for the duration of one
request, not a durable row, the same "sortable, opaque" shape regardless.
"""

from ulid import ULID


def new_assembly_id() -> str:
    return f"asm_{ULID()}"
