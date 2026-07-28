"""Prefixed ULID identifiers for Capability Manager rows.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids`/:mod:`ai_os_kernel.llm_gateway.ids`
exactly (data_model.md §2: "Prefixed ULID text ... Sortable, opaque,
safe in URLs and logs."). data_model.md does not give an example prefix
for ``catalog.pack_state_transitions`` specifically — its own prefix
list is illustrative, not exhaustive, the same reasoning ``call_`` was
already chosen under — so ``pkt_`` is a reasoned choice, not an
invented column or field.
"""

from ulid import ULID


def new_transition_id() -> str:
    return f"pkt_{ULID()}"
