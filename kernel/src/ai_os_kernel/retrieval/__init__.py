"""Retrieval — hybrid keyword + vector search over Knowledge and Memory.

PostgreSQL full-text search + pgvector, combined by Reciprocal Rank
Fusion (ADR-0013). Consumed only through the Context Manager; never
queried directly by an agent.

See docs/03_architecture/services/search_vector_search.md, ADR-0013.

Implemented so far: a real embedding writer
(:mod:`ai_os_kernel.retrieval.embedding_writer`, ``P02-S04-M11-T03``)
persisting a genuine ``embed()`` output to ``knowledge.embeddings``,
and real nearest-neighbour vector search over it
(:mod:`ai_os_kernel.retrieval.vector_search`, ``P02-S04-M11-T04``) via
pgvector's exact cosine-distance operator (no HNSW index yet — see
that module's own docstring for why). No keyword-search integration
here (it lives in :mod:`ai_os_kernel.persistence.
knowledge_keyword_search`), no Reciprocal Rank Fusion, no Retrieval
Service beyond these two real pieces, and no Context Manager resolver
reads from any of this yet.
"""
