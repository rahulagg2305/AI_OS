"""Prefixed ULID identifiers for LLM Gateway rows.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids` exactly (data_model.md
§2: "Prefixed ULID text ... Sortable, opaque, safe in URLs and logs.").
data_model.md does not give an example prefix for ``evaluation.llm_calls``
specifically — its own prefix list is illustrative, not exhaustive, the
same reasoning already used for ``lease_``/``stp_`` — so ``call_`` is a
reasoned choice, not an invented column or field.
"""

from ulid import ULID


def new_call_id() -> str:
    return f"call_{ULID()}"
