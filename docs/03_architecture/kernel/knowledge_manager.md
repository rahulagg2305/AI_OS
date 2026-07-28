# Knowledge Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Knowledge Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Knowledge Manager**, a core component of the AI_OS Platform Kernel.

The Knowledge Manager is responsible for storing, organizing, indexing, and retrieving the long-term, authoritative knowledge of the platform and of individual projects. It is one of the primary sources that the Context Manager uses when assembling context for Agents.

Knowledge must survive changes of LLM, changes of team members, and loss of chat history.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  

---

## 2. Design Goals

The Knowledge Manager must:

- Act as a reliable, long-term source of truth
- Support both platform-level knowledge and project-level knowledge
- Provide precise, permission-aware retrieval
- Remain domain-agnostic at the Kernel level
- Support versioning and traceability of knowledge items
- Integrate cleanly with the Context Manager and AI Context Packs
- Be fully observable

---

## 3. Types of Knowledge

The Knowledge Manager handles several categories of knowledge:

### Platform Knowledge
- Project Constitution and Governance documents
- Architecture documents
- Coding standards
- Capability Pack contracts
- ADRs
- Best practices and patterns
- Anti-patterns and known limitations

### Project Knowledge
- Requirements
- Architecture decisions for a specific product
- API specifications
- Database schemas
- Design documents
- Acceptance criteria
- Generated documentation

### Not Knowledge: Engineering Memory

Engineering memory is **not** handled by the Knowledge Manager. v1.0 of this document called it "related but distinct", which left the seam ambiguous. The boundary is now explicit and is by **authority and lifetime**:

| | Knowledge Manager | Memory Manager |
|---|---|---|
| Content | Documented, approved, authoritative | Experiential — what happened, what worked |
| Authority | **Highest** — the source of truth | Lower — **never overrides Knowledge** |
| Origin | `docs/`, specifications, ADRs, project artifacts | Workflow outcomes, promoted lessons |
| Lifetime | Long-lived, versioned | Workflow-scoped, or promoted and long-lived |

Both are **retrieval sources consumed through the Context Manager**; neither is queried directly by an agent. Definitions are in `../../20_glossary/glossary.md` §3, which is the single authority for these four terms (Knowledge, Memory, Context, Context Pack).

---

## 4. Core Responsibilities

- Ingest knowledge from approved sources (docs/, specs/, ADRs, etc.)
- Index knowledge for efficient retrieval
- Support semantic and structured queries
- Provide versioned access to knowledge items
- Enforce access rules where necessary
- Supply relevant knowledge to the Context Manager
- Maintain provenance (where each piece of knowledge came from)

---

## 5. High-Level Structure

```text
Knowledge Manager
│
├── Knowledge Ingestion
├── Knowledge Store
├── Indexer (structured + vector)
├── Query Engine
├── Version Manager
├── Provenance Tracker
└── Access / Filter Layer
```

---

## 6. Key Design Rules

- Documentation in the repository is the primary source of truth.
- The Knowledge Manager must not invent knowledge.
- Retrieved knowledge should carry provenance metadata.
- Knowledge used in any Agent invocation must be auditable.
- The same query under the same conditions should return consistent results (important for experiments).

---

## 7. Relationship with Other Components

- **Context Manager** is the main consumer of the Knowledge Manager.
- **AI Context Packs** can be viewed as curated, high-priority knowledge packages.
- **Memory Manager** handles more dynamic / experiential knowledge; Knowledge Manager handles more stable, documented knowledge.
- **Workflow Engine** and **Agents** never bypass the Context Manager to access knowledge directly in an uncontrolled way.
- **Evaluation / Experiment Engine** benefits from stable knowledge retrieval for fair comparisons.

---

## 8. Observability Requirements

Every knowledge retrieval must be able to record:

- What was requested
- What was returned
- Source documents / IDs
- Version of knowledge items
- Workflow ID / Trace ID correlation

---

## 9. Current Status

This document defines the design baseline for the Knowledge Manager.

Detailed storage technology choices, indexing strategy, schema for knowledge items, and concrete APIs will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Knowledge Manager Design  
6. Source Code
