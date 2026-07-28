# ADR-0003: Documentation-First Development

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/00_constitution/project_constitution.md`, `docs/DOCUMENTATION_INDEX.md`

---

## Context

AI_OS is built by a rotating set of AI models and human contributors, none of whom retain conversation history. If the authoritative description of the system lives in chat transcripts or in the heads of contributors, the project cannot survive a model change or a gap in activity. Knowledge must live in the repository.

## Decision

Requirements, architecture, interfaces, and contracts are written and approved in Markdown in this repository **before** the corresponding implementation. When implementation and documentation disagree, that is a defect. Documentation changes ship in the same change as the implementation they describe.

The documentation set is the single source of truth. Conversation history is never authoritative.

**Explicit limit:** documentation-first governs *decisions and contracts*, not exploratory work. Spikes and prototypes are permitted in `workspace/prototypes/` without prior documentation, on the condition that they are not promoted into `kernel/`, `platform_services/`, or `capability_packs/` until the corresponding decision or contract is documented. This prevents the principle from being used to justify either analysis paralysis or undocumented production code.

## Alternatives Considered

- **Code-first with documentation generated afterwards** — Faster per change; rejected because generated documentation records what was built, not what was intended, and offers no basis for review before cost is sunk.
- **Documentation-only-for-public-APIs** — Cheaper; rejected because the hardest AI_OS decisions are internal boundaries, which is exactly what would go unrecorded.

## Consequences

### Positive
- Any model or contributor can resume work from the repository alone.
- Architectural intent is reviewable before implementation cost is incurred.

### Negative
- Adds latency to every non-trivial change.
- Creates a real risk of documentation that is broad but shallow; mitigated by requiring contracts to be concrete (schemas, interfaces, and error models rather than bullet lists) and by the Quality Gates in `docs/03_architecture/quality/quality_gates_framework.md`.

### Neutral
- Requires the Documentation Index and status metadata to be actively maintained.

## Compliance

Complies with the Project Constitution, Articles 1 and 3.

## References

- `docs/19_roadmap/documentation_freeze.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Fully implemented

This is a process decision rather than code, and it is in force: contracts are documented before implementation, every step's rationale is recorded in `docs/19_roadmap/history/`, and `CLAUDE.md` makes the documentation set — never chat history — the resumption point for each session. `workspace/prototypes/` exists and is empty, so the prototype exemption has not yet been used.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
