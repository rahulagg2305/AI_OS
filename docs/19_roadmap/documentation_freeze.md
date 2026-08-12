# Documentation Baseline Record – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Documentation Baseline Record
**Version:** 2.1
**Status:** Approved — **historical record, superseded as a status document**
**Last Updated:** 2026-07-28 (header note added marking this a historical record; §3 and §8 annotated where they have been overtaken by implementation. The baseline record itself is unchanged.)

---

> ## ⚠️ This is a historical record, not current state
>
> **Read this document for what the documentation baseline of 2026-07-25 authorised, and why. Do not read it as a description of the project today.**
>
> It was written *before implementation began*, and its §4 and §8 sign-off ("approved for implementation from Stage A") have since been acted on: Stage A is process-complete, Stage B is well underway, and parts of Stage C have landed. It still serves two live purposes — it is the record of *why* the baseline was re-issued (§2), and it is where the accepted documentation gaps are listed (§5). Nothing else in it is current.
>
> **For current state, read instead:**
> - [`feature_inventory.md`](feature_inventory.md) — the authority on per-module completeness
> - [`feature_inventory.md`](feature_inventory.md) — per-module completion percentages
> - [`implementation_roadmap.md`](implementation_roadmap.md) — the Stage A–H sequence with per-deliverable delivery status
> - [`history/INDEX.md`](history/INDEX.md) — full chronological build history
> - [`../18_decision_log/README.md`](../18_decision_log/README.md) — the 25 ADRs, each with an appended implementation-status note

---

## 1. Purpose

Records the state of the AI_OS documentation baseline and what it does and does not authorise. Version 2.0 supersedes the v1.0 "Phase 0–6 Documentation Review & Freeze".

---

## 2. Why This Document Was Revised

Version 1.0 declared Phases 0–6 "Complete and frozen as the baseline". Three things were wrong with that, and correcting them matters because a false completion signal is worse than an honest gap list:

1. **52 of 68 documents carried `Status: Draft`.** Under Constitution Article 9, only *Approved* architecture documents govern — so most of the "frozen baseline" formally carried no authority.
2. **The technology decision layer did not exist.** No language, runtime, persistence, transport, API, or sandboxing decision had been made, and no ADR had been written despite seven being listed as Accepted. Implementation was therefore blocked by the Constitution's own prohibition on inventing architecture.
3. **Several documents contradicted each other** on Kernel composition, pack lifecycle, configuration precedence, agent identity, experiment ownership, and whether workflows were declarative or planned at runtime.

An independent architecture review of 2026-07-25 identified these; this document records the resolution.

---

## 3. Current Baseline State

| Category | State |
|---|---|
| Governance (Constitution, Governance Framework, Coding Standards) | **Approved.** Governance Framework amended by ADR-0022 (reproducibility) and extended with enforcement mechanisms |
| Architecture Decision Records | **25 ADRs Accepted** — see `../18_decision_log/README.md` |
| Requirements | **Approved.** Functional (FR-001…FR-116), non-functional (NFR-001…NFR-107), constraints (CON-001…CON-055) |
| Platform architecture | **Approved.** System Architecture v2.0, Technology Stack, Platform SDK Specification |
| Kernel subsystems | **Approved.** All 16 documents; Workflow Engine and LLM Gateway at v2.0 |
| Capability framework | **Approved.** Contract, Manifest Schema v2.0, and a machine-readable JSON Schema |
| Agents and workflows | **Approved.** Including contract-level specifications for the three Stage C agents and the Software Engineering pack's workflows |
| Security | **Approved.** Security Architecture with a numbered threat model (T1–T12) |
| Data | **Approved.** Data Model with tables, invariants, retention, and migration rules |
| APIs and interfaces | **Approved.** API Architecture, CLI, Dashboard, Voice |
| Quality and operations | **Approved.** Test Strategy, Observability Stack, Deployment Architecture, Operations Runbook |
| Documentation status | **62 documents Approved**, 0 Draft, 25 ADRs Accepted |

> **Annotation (2026-07-28).** Every "Approved" above still refers to *documentation* approval — that a contract is specified and governs — never to the existence of an implementation. Several rows describe subsystems with no code at all (Evaluation Engine, Event Bus, Knowledge Manager, Memory Manager, Quality Gate Engine, Traceability Engine, Dashboard, Voice, Speech Gateway), and the "Platform SDK Specification" row describes a package that does not exist yet: `platform_sdk/` holds exactly one real file, `schemas/manifest.schema.json`. See [`feature_inventory.md`](feature_inventory.md) for what is built.

---

## 4. What the Baseline Authorises

Implementation may begin at **Stage A** and proceed through the Implementation Roadmap. Specifically, the baseline now provides what an implementer needs and previously lacked:

- a decided technology stack, every element ADR-backed;
- a specified Platform SDK — the pack boundary as interfaces rather than prose;
- a machine-enforceable manifest schema;
- a threat model with named controls;
- concrete, measurable NFR targets;
- requirements with stable IDs, so traceability has a root;
- contract-level specifications for the agents and workflows of the first vertical slice.

---

## 5. Known Gaps (accepted, not hidden)

These are deliberately deferred with recorded triggers, listed here so no one mistakes silence for coverage:

| Gap | Status |
|---|---|
| Manifest signing | Not in v1. Provenance controlled by install path + human-approved activation (`../09_security/security_architecture.md` §8) |
| Multi-tenancy | Not in v1. Single tenant; the project boundary is organisational, not a security boundary (ADR-0023) |
| gVisor / micro-VM sandbox as default | Available as configuration; not the default (ADR-0016) |
| Agent specifications beyond Stage C | Template defined; each written before its stage begins (`../05_agents/agent_specifications.md` §7) |
| NFR values marked **(baseline)** | First-principles estimates; must be re-baselined against measurement by end of Stage D |
| MCP integration surface | Deferred to a future Capability Pack with its own ADR (ADR-0014) |
| Architecture diagrams beyond ASCII | `03_architecture/diagrams/` is empty; ASCII diagrams are in the documents |

Full list with triggers: `../18_decision_log/README.md` §Open Decision Points.

---

## 6. Change Control

The baseline is **not** immutable — freezing documentation would contradict the requirement that documentation stay current with implementation. Instead:

- Any change contradicting an ADR requires a new ADR superseding it.
- Any change to a contract (SDK Protocol, manifest schema, API, data model) requires a version increment and a migration note.
- Implementation experience is expected to reveal detail this baseline lacks; adding that detail is normal, and doing so does not require an ADR unless a decision changes.
- Corrections to a document that make it *match* an existing decision are ordinary maintenance.

---

## 7. Phase Terminology

To end a persistent source of confusion: the numbered "Phases 0–6" used in earlier documents referred to **documentation-authoring phases**, which were then conflated with delivery phases in `PROJECT_INDEX.md`. That numbering is retired.

There is now **one** sequence: the lettered **Stages A–H** in `implementation_roadmap.md`. Documentation phases are no longer used or referenced.

---

## 8. Sign-off

The documentation baseline is **approved for implementation from Stage A**, with the gaps in §5 accepted and tracked.

> **Annotation (2026-07-28).** This sign-off has been acted on. Implementation started, Stage A is process-complete (its remaining exit criteria are OTLP export and the Compose observability profile), Stage B is well underway, and a real Software Engineering pack plus a real ADR-0016 Tier 1 sandbox have landed from Stage C. This section is retained as the record of the authorisation, not as a statement of where work stands — see [`feature_inventory.md`](feature_inventory.md).

---

## 9. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Architecture Decision Records
4. System Architecture and subsystem documents
5. This baseline record
6. Source Code
