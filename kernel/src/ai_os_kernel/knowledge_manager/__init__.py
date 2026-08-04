"""Knowledge Manager — stable, documented, authoritative content.

Constitution, architecture documents, specifications, ADRs, coding
standards, and per-project requirements/design. Ranks above Memory in
authority — see docs/20_glossary/glossary.md §3 for the Knowledge vs.
Memory vs. Context distinction.

See docs/03_architecture/kernel/knowledge_manager.md.

Implemented so far: a real Indexing component
(:mod:`ai_os_kernel.knowledge_manager.indexing`, ``P02-S04-M09-T03``)
turning real source content into real, chunked
``knowledge.documents``/``knowledge.chunks`` rows through the real
:class:`~ai_os_kernel.persistence.knowledge_writer.SqlKnowledgeWriter`,
with a real archive-and-replace policy for a changed ``source_uri``.
Still not implemented: Query Engine, Version Manager, Provenance
Tracker, and Access/Filter Layer as components of this package (their
real prerequisites exist one layer down — see
docs/03_architecture/kernel/knowledge_manager.md's own Implementation
Status).
"""
