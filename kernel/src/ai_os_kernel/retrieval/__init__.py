"""Retrieval — hybrid keyword + vector search over Knowledge and Memory.

PostgreSQL full-text search + pgvector, combined by Reciprocal Rank
Fusion (ADR-0013). Consumed only through the Context Manager; never
queried directly by an agent.

See docs/03_architecture/services/search_vector_search.md, ADR-0013.
Not yet implemented — Implementation Roadmap Stage B.
"""
