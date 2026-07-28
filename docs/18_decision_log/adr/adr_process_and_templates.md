# Decision Log (ADR) Process & Templates – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Decision Log (ADR) Process & Templates  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (added §5.1, the appended implementation-status note convention)

---

## 1. Purpose

This document defines how Architecture Decision Records (ADRs) and the Decision Log are managed in AI_OS.

Every significant architectural, technical, or governance decision must be recorded so that:

- The project remains understandable by any future LLM or human
- Decisions are traceable and auditable
- Context is never lost when changing models or team members

This document is subordinate to the Project Constitution and AI Governance Framework.

---

## 2. When to Write an ADR

An ADR is mandatory for:

- Choice of major technologies or frameworks
- Architectural style decisions
- Changes to the Kernel or Capability Pack contracts
- Introduction of new cross-cutting concerns
- Significant changes to workflow, agent, or quality gate design
- Any decision that affects multiple parts of the system
- Deviations from existing standards

Routine implementation details do **not** require an ADR.

---

## 3. ADR Lifecycle

1. Proposed  
2. Accepted  
3. Deprecated (optional)  
4. Superseded (by a newer ADR)

Only **Accepted** ADRs are considered active.

---

## 4. ADR File Naming Convention

```text
ADR-XXXX-short-title.md
```

Examples (these are the actual first two ADRs):
- `ADR-0001-modular-capability-pack-architecture.md`
- `ADR-0002-llm-gateway-single-entry-point.md`

Files are stored in:

```text
docs/18_decision_log/adr/
```

---

## 5. Standard ADR Template

```markdown
# ADR-XXXX: Title

**Status:** Proposed | Accepted | Deprecated | Superseded  
**Date:** YYYY-MM-DD  
**Decision Makers:**  
**Related Documents:**  

---

## Context

What is the issue or force that requires a decision?

## Decision

What is the change or choice that we are making?

## Alternatives Considered

- Alternative 1 – pros / cons
- Alternative 2 – pros / cons
- ...

## Consequences

### Positive
- ...

### Negative
- ...

### Neutral
- ...

## Compliance

Does this decision comply with the Project Constitution and Governance Framework?

## References

- Links to related documents, discussions, or prior ADRs
```

### 5.1 Appended implementation-status notes (added 2026-07-28)

An Accepted ADR records a decision, not its delivery, and a reader arriving at an ADR has no way to tell which parts of it exist in code. To close that gap without violating ADR immutability, every ADR carries an **appended, clearly-delimited implementation-status note at the very end of the file**:

```markdown
---

## Implementation Status (appended YYYY-MM-DD — not part of the Accepted decision)

**Status in code:** Fully implemented | Partially implemented | Not yet implemented

<one or two concrete sentences on exactly what exists and what does not>

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
```

Rules:

- The note is **append-only and additive**. It never edits the ADR's Context, Decision, Alternatives, Consequences, Compliance, References, `Status:` line, or `Date:`. Reversing or revising a decision still requires a superseding ADR.
- The note is **derived, not authoritative**. `docs/19_roadmap/feature_inventory.md` governs on any conflict.
- It states what is *not* built as explicitly as what is. A note that lists only progress is a defect.
- A pre-existing note of a different kind (for example ADR-0016's "Implementation naming note", which sits inside the Decision section) is left in place; the status note is added alongside it, not merged into it.

---

## 6. Decision Log Index

A central index of all ADRs shall be maintained at:

```text
docs/18_decision_log/README.md
```

The index must list:

- ADR number
- Title
- Status
- Date
- Short summary

---

## 7. Current Decision Log

**25 ADRs are Accepted.** The complete, current index — with summaries and the register of open decision points — is maintained at:

```text
docs/18_decision_log/README.md
```

That index is the authoritative list. This document defines only the *process* and *template*; it deliberately does not duplicate the ADR list, because a second copy would drift (as it did: v1.0 of this document listed seven ADRs as Accepted at a time when none had been written).

---

## 8. Governance Rules

- ADRs must be reviewed before being marked Accepted.
- Superseding an ADR requires a new ADR that explicitly references the old one.
- The Decision Log is part of the project’s single source of truth.

---

## 9. Current Status

This document establishes the Decision Log process and template. ADR-0001 through ADR-0025 are written and Accepted; the index at `../README.md` is maintained alongside them.

As of 2026-07-28 all 25 carry an appended implementation-status note (§5.1): **3 fully implemented, 16 partially implemented, 6 not yet implemented**. No Accepted decision has been contradicted by implementation — every gap is an unbuilt part of an accepted decision. The index's `In code` column summarises this.

**Recording a deferral.** Where a decision is deliberately postponed, it is recorded in the index's *Open Decision Points* table with the trigger condition that will require deciding it. A deferral with no recorded trigger is indistinguishable from an oversight, so the trigger is mandatory.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. This Decision Log Process  
5. Individual ADRs  
6. Source Code
