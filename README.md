# AI_OS

**AI Operating System for Autonomous Software Engineering**

AI_OS is a modular, LLM-agnostic, production-grade platform designed to autonomously create, analyze, and enhance software systems through multi-agent collaboration.

It is **not** a coding assistant.
It is an AI Operating System that transforms structured specifications into production-ready software while maintaining architecture, governance, observability, traceability, and quality throughout the software lifecycle.

---

## Vision

Build a platform that can:

- Create complete software products from structured specifications
- Analyze, understand, and modernize existing software systems
- Compare multiple LLMs using measurable engineering benchmarks
- Support multiple domains through installable Capability Packs
- Provide a configurable dashboard and voice interface (Jarvis)
- Preserve project knowledge so development can continue across different AI models

---

## Repository Goals

This repository is the **single source of truth** for AI_OS.

Every design decision, requirement, specification, architecture document, implementation, and knowledge artifact must be maintained here.

**Documentation is considered authoritative.**

---

## Core Principles

1. Documentation First
2. Configuration over Code
3. Interface-Driven Design at real seams
4. Capability Pack Architecture
5. LLM Agnosticism
6. Human Governance for Critical Decisions
7. Observability by Default
8. Traceability by Design
9. Reproducibility — pinned conditions, deterministic platform behaviour, recorded non-determinism

---

## Current Status

**Documentation baseline:** Approved
**Architecture decisions:** 25 ADRs Accepted
**Current stage:** **Stage B – Minimum Viable Kernel, underway.** Stage A is process-complete but not exit-criteria-complete; some Stage C work (a real Capability Pack, a real Tier 1 sandbox) landed early.
**Tests:** 849 passing, 11 skipped (opt-in live-provider), 0 failing. `mypy --strict` and `ruff` clean.

The technology stack is decided and every choice is backed by an Architecture Decision Record. Implementation follows `docs/19_roadmap/implementation_roadmap.md`.

**What works end to end today:** a five-agent Software Engineering Capability Pack in which four agents are chained into one real declared workflow (`se.delivery_pipeline`) — it takes a requirement, produces a design, writes a real file, executes it, and documents the result, with all generated-code execution inside a real, live-verified, network-isolated OCI container sandbox.

**What does not exist yet:** the Dashboard, the CLI, the Voice/Jarvis pack, Project Intelligence, Benchmarking, the Platform SDK package, and several Kernel subsystems (Event Bus, Quality Gate Engine, Evaluation Engine, Traceability Engine, Knowledge/Memory Managers) plus all Platform Services. Do not assume a directory has content because it is named in the docs — check `docs/process/folder_structure.md`.

Run the Kernel API:

```sh
uv sync
uv run uvicorn ai_os_kernel.entrypoints.api:app --reload
```

**The three live-status documents** — read these rather than this summary for current state:

- `docs/19_roadmap/implementation_status.md` — **read first, every session.** Short: current stage, what exists, blockers, next step.
- `docs/19_roadmap/feature_inventory.md` — per-module completion tracker; the authority on "how done is X."
- `docs/19_roadmap/history/INDEX.md` — full build history by milestone.

See `kernel/README.md` for Kernel-specific detail.

---

## Technology Stack

Full detail: `docs/03_architecture/platform/technology_stack.md`.

- **Python 3.12** · asyncio · `mypy --strict` · Pydantic v2
- **uv** workspace; each Capability Pack is its own distribution
- **PostgreSQL 16** with an append-only event log; **pgvector** for hybrid search
- **Redis 7** for caching and rate limiting
- **FastAPI** REST + WebSocket; OpenAPI 3.1
- **React 19 + TypeScript + Vite** dashboard
- **OpenTelemetry** telemetry; hash-chained audit log
- **Ephemeral OCI container sandboxes** for all generated-code execution
- **GitHub Actions** CI with pytest, testcontainers, ruff, mypy

---

## Architectural Invariants

Enforced by mechanism, not convention:

- All model access goes through the **LLM Gateway**. No pack may import a provider SDK.
- **Agents never communicate directly.** The Workflow Engine is the sole orchestrator and owns all state.
- Packs interact with the platform **only through the Platform SDK**.
- **Untrusted code runs only in a sandbox** with no network, no secrets, and no host access.
- **Authority only narrows** along the invocation chain; no LLM output can grant a permission.
- Blocking Quality Gates cannot be skipped; an approval timeout never implies approval.

---

## Getting Started (For Humans & LLMs)

Before making any change, read in this order:

1. `README.md`
2. `PROJECT_INDEX.md`
3. **`CLAUDE.md`** — the working process: approval workflow, standing rules, known environment quirks
4. **`docs/19_roadmap/implementation_status.md`** — what actually exists right now (short by design)
5. `docs/00_constitution/` — Constitution and Governance Framework
6. `docs/20_glossary/glossary.md` — the vocabulary is precise
7. `docs/18_decision_log/README.md` — all 25 ADRs
8. `docs/03_architecture/platform/` — system architecture, technology stack, Platform SDK (note: the SDK document is a *specification*; no SDK package exists yet)
9. `docs/02_requirements/` — requirements, NFRs, constraints
10. Relevant subsystem documents

**Do not rely on previous conversation history.**

Complete index with per-document status: `docs/DOCUMENTATION_INDEX.md`.
Process/working rules: `docs/process/` (see `docs/process/files_to_read_first.md` for what to reach for and when).

> **A note on reading architecture documents.** Every subsystem document under `docs/03_architecture/` now carries an **Implementation Status** section near the top stating honestly what is built and what is not. Read that section before assuming the rest of the document describes working software — several describe subsystems that are 0% built.

---

## AI Development Rules

Every AI model working on this repository must follow these rules:

- Do not invent requirements or architecture
- Documentation is the source of truth
- Record technology and architecture decisions as ADRs **before** implementing them
- Update documentation whenever implementation changes, in the same change
- Maintain traceability between requirements, architecture, modules, and tests
- Keep the platform modular, configurable, and LLM-agnostic
- Follow the coding standards in `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`
- Never weaken a security control or a quality gate to make something pass

---

## Success Criteria

The platform should enable any AI model to:

- Understand the project with minimal onboarding
- Continue development without prior chat history
- Preserve architectural consistency
- Produce production-grade, maintainable software
- Extend the platform without modifying the core architecture
