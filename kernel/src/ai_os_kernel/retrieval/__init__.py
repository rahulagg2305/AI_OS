"""Retrieval — hybrid keyword + vector search over Knowledge and Memory.

PostgreSQL full-text search + pgvector, combined by Reciprocal Rank
Fusion (ADR-0013). Consumed only through the Context Manager; never
queried directly by an agent.

See docs/03_architecture/services/search_vector_search.md, ADR-0013.

Implemented so far (``P02-S04-M11-T03``): a real embedding writer
(:mod:`ai_os_kernel.retrieval.embedding_writer`) — persists a genuine
``embed()`` output to ``knowledge.embeddings``. No keyword/vector
search, no Reciprocal Rank Fusion, no Retrieval Service, and no
Context Manager resolver reads from any of this yet.
"""
