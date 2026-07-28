# ADR-0008: Primary Language and Runtime — Python 3.12 with Strict Typing

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/platform/technology_stack.md`, `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`

---

## Context

No language or runtime had been chosen for AI_OS, which blocked all implementation: the Constitution forbids inventing architecture, so no implementer could choose unilaterally. The choice must serve a platform whose critical path is LLM orchestration, retrieval, document processing, and evaluation, and which must run long-lived asynchronous workflows with heavy I/O concurrency.

An important distinction: this decision governs the language **AI_OS itself is written in**. It places no constraint on the languages of the software AI_OS *generates* — that is handled by Tools executing inside sandboxes ([ADR-0016](ADR-0016-tool-execution-sandboxing.md)) and is deliberately open-ended.

## Decision

**The Platform Kernel, Platform Services, Platform SDK, Capability Packs, CLI, and tooling are written in Python 3.12** (minimum 3.12, tested on 3.12 and 3.13).

Mandatory language-level discipline:

| Concern | Decision |
|---|---|
| Typing | `mypy --strict` on `kernel/`, `platform_sdk/`, `platform_services/`, and packs. No untyped defs, no implicit `Any` at boundaries. |
| Interfaces | `typing.Protocol`, structurally typed, declared in `platform_sdk/contracts/`. Not ABCs — Protocols keep adapters free of inheritance coupling. |
| Data models | Pydantic v2 for every external boundary (manifests, API bodies, agent I/O, tool I/O, events, config). Frozen dataclasses for internal value objects where validation is not needed. |
| Concurrency | `asyncio`. The Kernel is async end to end; blocking calls are isolated in worker threads via `asyncio.to_thread`, never called on the event loop. |
| Errors | Typed exception hierarchy rooted at `AiOsError`, mapped to the platform error taxonomy in `docs/03_architecture/workflow/error_handling_retry.md`. |

The Dashboard frontend is the single exception and is TypeScript/React ([ADR-0018](ADR-0018-dashboard-technology-stack.md)).

## Alternatives Considered

- **TypeScript / Node.js everywhere** — Attractive for one language across backend and Dashboard, with genuinely good async ergonomics. Rejected because the retrieval, embedding, document-parsing, AST-analysis, and evaluation ecosystem AI_OS depends on is Python-first; on Node these become either shell-outs or second-class ports. The Project Intelligence pack in particular would be materially harder.
- **Go** — Best raw concurrency and single-binary deployment, strong typing. Rejected because the AI/retrieval ecosystem is comparatively thin, meaning more of the platform's differentiating logic would be written from scratch, and because generics-era Go is more verbose for the schema-heavy, adapter-heavy code that dominates this codebase.
- **C# / .NET** — Excellent type system and tooling, first-class async. Rejected for the same ecosystem reason as Go, plus a smaller pool of AI-engineering reference material for a project explicitly designed to be continued by AI models.
- **Rust** — Rejected: the safety and performance benefits do not pay for the iteration cost on an I/O-bound orchestration platform.
- **Polyglot (Go kernel + Python packs)** — Rejected: doubles the SDK, the contract surface, the CI matrix, and the onboarding burden for no benefit that a single async Python process does not already provide at this scale.

Python's weaknesses are accepted with mitigations: the GIL is largely irrelevant for an I/O-bound workload and CPU-bound work is pushed into sandboxed subprocesses; dynamic typing is contained by `mypy --strict` and Pydantic at every boundary.

## Consequences

### Positive
- Direct access to first-party provider SDKs (`anthropic`, and others behind Gateway adapters), pgvector clients, parsers, and evaluation tooling.
- One language, one toolchain, one CI matrix for the entire backend.
- The largest available body of reference material for AI models continuing this work.

### Negative
- Runtime type errors remain possible where third-party libraries are untyped; mitigated by adapter-level validation and `disallow_untyped_calls`.
- CPU-bound analysis (large-repo parsing) must be parallelised across processes rather than threads.
- Requires deliberate discipline to keep async code from blocking; enforced by lint rules and review checklist.

### Neutral
- Naming conventions become Python-idiomatic (`snake_case` modules, `PascalCase` classes, no `I`-prefixed interfaces); the Coding Standards are updated accordingly.

## Compliance

Complies with the Constitution's requirement that architecture be documented and approved before implementation. Supersedes no prior decision; it fills a gap.

## References

- `docs/03_architecture/platform/technology_stack.md`
- [ADR-0009](ADR-0009-packaging-and-dependency-management.md), [ADR-0010](ADR-0010-composition-and-dependency-injection.md)

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The language-level discipline holds: Python 3.12 (`requires-python = ">=3.12,<3.14"`), `mypy --strict` clean across 283 source files, `typing.Protocol` rather than ABCs at every seam, Pydantic v2 at every external boundary, and asyncio end to end. The one decided element missing is the typed exception hierarchy rooted at `AiOsError` — no such root class exists anywhere; each subsystem defines its own independent error hierarchy instead (`sandbox/errors.py`, `secrets_manager/errors.py`, `capability_manager/errors.py`, and others).

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
