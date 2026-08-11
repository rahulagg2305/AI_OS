# Traceability Model – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Traceability Model (detailed)  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-11, `P04-S02-M16-T05`)

**A real writer and both real queries exist, and the writer now has its first real production caller** — see `../kernel/traceability_engine.md`'s own Implementation Status for the full detail. `SqlTraceLinkWriter` genuinely records/closes `trace.links` rows, upserting both endpoint `trace.artifacts` rows inline; `find_affected_artifacts()` genuinely answers §7's own "what is affected if I change this module?" query via a real, bidirectional, cycle-safe recursive CTE; `find_uncovered_requirements()` genuinely answers §7's own "which requirements are not covered by tests?" query.

**Updated 2026-08-11 (`P04-S02-M16-T04`, closing risk register R-018's own worst "proven but idle" instance): the writer is no longer idle.** From `P04-S02-M16-T01` until this date, all three of the above were `done` yet nothing in the codebase ever constructed the writer in production — the health audit (2026-08-11) found zero production importers of `traceability_engine` outside its own package, and this section itself said so ("No Agent/Workflow caller yet"). Now `ai_os_kernel.routes.delivery_pipeline` records a real §4 **"Workflow Run produced Documentation"** link — the exact relationship this document's own §4 bullet list names — for every `se.delivery_pipeline` run that genuinely produces its documentation output, through a new bootstrap-wired `app.state.trace_link_writer` (`ai_os_kernel.workflow_engine.delivery_pipeline.record_documentation_traceability_link`). A real, product-owner-decided nuance recorded so it is not re-litigated: the link is written the moment the documentation artifact genuinely exists (the run pauses at its own `approve-git-push` human-approval step *after* documentation, so waiting for full `COMPLETED` would have left this write site nearly dead), and it is `confirmed` confidence, `process` created-by-type — every field derived from the real run, none fabricated. The read side (impact/coverage over §6.6 HTTP routes) remains genuinely unbuilt, split out as `P04-S02-M16-T05`; the root `traceability/` directory still has no tracked content.

**Updated 2026-08-11 (`P04-S02-M16-T05`): the read side is real too — R-018's Traceability instance is closed on both halves.** `ai_os_kernel.routes.traceability` exposes §6.6's own `GET /api/v1/traceability/impact/{id}` (over the impact query) and `GET /api/v1/traceability/coverage` (over the coverage query), proven over real, writer-seeded rows through the real `build_app()` composition. The one disclosed route-shape choice: `impact/{id}` carries the `external_id` and requires `artifact_type` as a query param, since an artifact's real identity here is the `(artifact_type, external_id)` pair. `GET /traceability/query` (raw link graph) stays unbuilt — a separate shape decision.

Consequence: the "Traceability by Design" principle now has one real, automated recording path (a delivery-pipeline run's own produced-documentation link) **and a real read path over it** (impact/coverage HTTP routes), no longer zero on either side — but it is still one link type from one workflow, not yet the full requirement→architecture→module→test chain the model describes. Stage D deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the detailed **Traceability Model** for AI_OS.

It specifies the types of artifacts that participate in traceability, the relationships between them, and the rules for maintaining those relationships. This model is implemented by the Traceability Engine and used for impact analysis, coverage analysis, and governance.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Traceability Engine Design  
4. System Architecture  

---

## 2. Design Goals

The Traceability Model must:

- Make relationships between key artifacts explicit
- Support queries such as impact analysis and coverage analysis
- Remain practical to maintain
- Support both automated and human-assisted link creation
- Serve governance and quality needs

---

## 3. Core Artifact Types

The following artifact types participate in the model:

- Requirement
- Architecture Element / Decision (including ADRs)
- Design Element
- Module / Component
- Source File / Code Artifact
- Test Case / Test Suite
- Quality Gate Result
- Workflow / Experiment Run
- Documentation Artifact
- Release / Version

Additional types may be added later if necessary.

---

## 4. Core Relationships

Typical relationships:

- Requirement **is implemented by** Module / Component
- Requirement **is verified by** Test Case
- Architecture Element **is realized by** Module / Component
- ADR **affects** Module / Component / Requirement
- Module / Component **is contained in** Source Files
- Test Case **covers** Requirement or Module
- Workflow Run **produced** Code Artifact / Documentation / Release
- Quality Gate Result **applies to** Workflow Run / Artifact

Relationships should be directional and named clearly.

---

## 5. Link Attributes

Each traceability link should support at least:

- Source artifact ID and type
- Target artifact ID and type
- Relationship type
- Provenance (who/what created the link and when)
- Confidence or status (confirmed, inferred, provisional) when useful
- Version or revision information when applicable

---

## 6. Maintenance Rules

- Prefer explicit link creation by Agents or controlled processes over pure inference.
- When artifacts are deleted or superseded, related links must be updated or closed.
- Missing critical links (e.g., requirement with no tests) should be detectable and reportable.
- Traceability data is part of the project’s long-term knowledge and must be treated accordingly.

---

## 7. Key Queries the Model Must Support

- What implements this requirement?
- What tests verify this requirement?
- What is affected if I change this module?
- Which requirements are not covered by tests?
- Which ADRs affect this component?
- What did this workflow run produce?

---

## 8. Relationship with Other Components

- **Traceability Engine** stores and queries the model.
- **Agents** (especially Requirements, Architecture, Documentation, QA, Release) create and update links.
- **Workflow Engine** provides the context in which many links are created.
- **Knowledge Manager** may surface traceability information.
- **Dashboard** presents matrices and impact views.
- **Evaluation Engine** may use coverage-related signals.

---

## 9. Current Status

This document defines the detailed Traceability Model.

Concrete schemas, storage formats, and agent responsibilities for maintaining links will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Traceability Engine Design  
4. Traceability Model  
5. Source Code
