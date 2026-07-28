# Documentation Baseline Record – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Documentation Baseline Record
**Version:** 2.0
**Status:** Approved
**Last Updated:** 2026-07-25

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

---

## 9. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Architecture Decision Records
4. System Architecture and subsystem documents
5. This baseline record
6. Source Code
