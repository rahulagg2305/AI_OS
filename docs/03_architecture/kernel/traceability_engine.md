# Traceability Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Traceability Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-08, `P04-S02-M16-T03`)

**Coverage analysis is real too (FR-115)** — `traceability_engine.coverage_query.find_uncovered_requirements()`: every real requirement artifact with no real, open, `confirmed`-confidence `verifies` link pointing at it. A third real, product-owner-decided design fork: only `confirmed` confidence discharges the coverage obligation — a merely `inferred`/`provisional` link (an agent's own unreviewed guess) does not, so a real gap cannot hide behind an unconfirmed link. Proven against real Postgres: a confirmed verifying link is recognized as coverage; a provisional-only link still reports the requirement as uncovered; a requirement with no verifying link at all (only an unrelated relationship) is reported; a verifying link for a *different* requirement does not cross-cover; closing a previously-confirmed verifying link makes the requirement uncovered again. No recursion needed — coverage is a direct property of each requirement's own incoming links.

**The `trace.links` writer is now real — the first writer either table has ever had.** `traceability_engine.link_writer.SqlTraceLinkWriter.record_link()` upserts both endpoint `trace.artifacts` rows inline (keyed deterministically off their own real-world identity — `artifact_type`+`external_id`, not a random id, a real design fork resolved by the product owner: see that module's own docstring) and records the `trace.links` row, idempotently for an already-open identical `(source_key, relationship, target_key)` triple. `close_link()` is real too. Proven against real Postgres: two independent calls naming the same real artifact converge on one row; re-asserting an open link is a no-op, not a constraint violation; closing then re-asserting opens a genuinely new row; every closed-vocabulary field is validated before any real database call.

**Impact analysis is real too** — `traceability_engine.impact_query.find_affected_artifacts()`, data_model.md §8's own documented "recursive CTEs over trace.links" mechanism, the first recursive CTE anywhere in this codebase. A second real, product-owner-decided design fork: traversal is bidirectional (an artifact's own links are followed as both source and target), since neither this document nor traceability_model.md §4 names a canonical per-relationship direction, and a one-directional query risked silently missing a real, recorded relationship. Only open (`closed_at IS NULL`) links are traversed. Proven against real Postgres: a direct link makes both endpoints mutually reachable; impact is genuinely transitive across a real multi-hop chain; a real `A --affects--> B --affects--> A` cycle terminates correctly (the recursive path-tracking cycle guard is real, not decorative) and reports each artifact exactly once; a closed link is not traversed; an artifact with no links returns none.

**Still nothing**: no Agent/Workflow caller — nothing invokes this writer or either query in a real composition yet; the root `traceability/` directory still has no tracked content. Data model: `../traceability/traceability_model.md`.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the design of the **Traceability Engine**, a core component of the AI_OS Platform Kernel.

The Traceability Engine is responsible for maintaining explicit, queryable links between Requirements, Architecture, Design, Implementation, Tests, Documentation, and Releases. It enables impact analysis, coverage analysis, and compliance with the “Traceability by Design” principle.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Workflow Architecture  

---

## 2. Design Goals

The Traceability Engine must:

- Maintain reliable links across the software lifecycle
- Support queries such as “Which requirements are implemented by this module?” or “Which tests cover this requirement?”
- Enable impact analysis (“If I change this, what is affected?”)
- Integrate with Workflow outcomes, Agents, and Documentation
- Remain domain-agnostic at the Kernel level
- Be auditable and version-aware

---

## 3. Core Responsibilities

- Record traceability links as they are created or discovered
- Maintain the traceability graph / matrix
- Answer traceability queries
- Support impact analysis
- Provide data to the Dashboard and to documentation generation
- Keep links consistent when artifacts evolve (as far as practical)

---

## 4. Key Traceability Relationships

Typical relationships that must be supported:

- Requirement → Architecture Element
- Architecture Element → Design / Module
- Module / Component → Source Files
- Requirement → Test Cases
- Architecture Decision (ADR) → Affected Components
- Workflow / Experiment → Produced Artifacts

---

## 5. High-Level Structure

```text
Traceability Engine
│
├── Link Recorder
├── Traceability Store
├── Query Engine
├── Impact Analyzer
├── Consistency Checker
└── Observability Hook
```

---

## 6. Key Design Rules

- Traceability links should be created explicitly (by Agents, Workflows, or controlled processes), not invented.
- Links must carry provenance (who/what created them and when).
- The system should make missing traceability visible (e.g., requirements without tests).
- Traceability data is part of the project’s long-term knowledge.

---

## 7. Relationship with Other Components

- **Workflow Engine** and **Agents** (especially Documentation, Requirements, Architecture, QA agents) create and update links.
- **Knowledge Manager** may store or surface traceability-related knowledge.
- **Evaluation Engine** can use traceability coverage as a quality signal.
- **Dashboard** presents traceability matrices and impact views.
- **Context Manager** may use traceability information when assembling context.

---

## 8. Observability & Audit

Changes to the traceability model should be recorded so that it is possible to understand how the links evolved over time.

---

## 9. Current Status

This document defines the design baseline for the Traceability Engine.

Detailed data models, query APIs, and integration points with specific Agents will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Traceability Engine Design  
6. Source Code
