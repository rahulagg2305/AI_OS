"""Prefixed ULID identifiers for ``knowledge`` schema rows.

Mirrors :mod:`ai_os_kernel.workflow_engine.ids`/:mod:`ai_os_kernel.
llm_gateway.ids`/:mod:`ai_os_kernel.capability_manager.ids`/:mod:`ai_os_kernel.
context_manager.ids` exactly (data_model.md §2: "Prefixed ULID text ...
Sortable, opaque, safe in URLs and logs."). data_model.md does not give
an example prefix for ``knowledge.documents``/``knowledge.chunks``/
``knowledge.embeddings`` specifically — its own prefix list is
illustrative, not exhaustive, the same reasoning already used for
``pkt_``/``call_``/``asm_`` — so ``doc_``/``chunk_``/``emb_`` are
reasoned choices, not invented columns or fields.
"""

from ulid import ULID


def new_document_id() -> str:
    return f"doc_{ULID()}"


def new_chunk_id() -> str:
    return f"chunk_{ULID()}"


def new_embedding_id() -> str:
    return f"emb_{ULID()}"
