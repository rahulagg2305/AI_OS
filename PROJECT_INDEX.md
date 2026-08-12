# PROJECT_INDEX.md

**AI_OS Project Index**
**Version:** 2.1
**Status:** Approved
**Current Stage:** Stage B – Minimum Viable Kernel (underway); Stage A process-complete but not exit-criteria-complete
**Last Updated:** 2026-07-28 (documentation consolidation audit — stage status corrected, repository structure table marked real-vs-planned, links added to the process docs and live status trackers)

---

## Purpose

This document is the **primary entry point** for both humans and AI models.

Every new developer or AI model must start here before working on the project. Its purpose is to explain what AI_OS is, show the current state, direct readers to the correct documentation, and let any model continue development without prior chat history.

> **If you are an AI session starting work, read `CLAUDE.md` at the repository root immediately after this file.** It carries the working process (approval workflow, standing rules, known environment quirks) that this document does not, and points at the short live-status file you must read before anything else.

---

## What is AI_OS?

AI_OS (AI Operating System) is a modular, LLM-agnostic, production-grade platform for autonomous software engineering through multiple specialized agents.

Its primary objectives are:

- Create complete production-grade software products from structured specifications
- Analyze, understand, and enhance existing or legacy software systems
- Benchmark multiple LLMs using measurable engineering metrics
- Support future domains through installable Capability Packs
- Provide governance, observability, traceability, quality control, and a configurable voice interface (Jarvis)

AI_OS is **not** a coding assistant. It is an extensible AI platform that orchestrates specialized agents while maintaining architectural consistency and governance.

---

## Current Status

**Documentation baseline:** Approved (`docs/19_roadmap/documentation_freeze.md`)
**Architecture decisions:** 25 ADRs Accepted (`docs/18_decision_log/README.md`)
**Current stage:** **Stage B – Minimum Viable Kernel, underway.** Stage A is process-complete but not exit-criteria-complete (OTLP export and the Compose observability profile remain). Some Stage C work has landed early — a real Capability Pack and a real ADR-0016 Tier 1 sandbox.
**Tests:** 849 passing, 11 skipped (opt-in live-provider tests), 0 failing. `mypy --strict` and `ruff` clean.

**This table is a summary. Three documents are the live, authoritative view — read them, not this, for current state:**

| Document | What it tells you |
|---|---|
| `docs/19_roadmap/feature_inventory.md` | **Read this first.** The authority on per-module completeness (2026-08-11 ruling). `implementation_status.md` is **superseded** — do not read it for status. |
| `docs/19_roadmap/feature_inventory.md` | The per-module completion tracker — every module with a percentage, a status category, and what remains. The authority on "how done is X." |
| `docs/19_roadmap/history/INDEX.md` | Full chronological build history, split by milestone. |

**What genuinely works end to end today:** a five-agent Software Engineering Capability Pack (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) in which four are chained into one real declared workflow (`se.delivery_pipeline`) that takes a requirement, produces a design, writes a real file, executes it, and documents the result — all generated-code execution inside a real, live-verified, network-isolated OCI container sandbox.

**What does not exist yet:** the Dashboard, the CLI, the Voice/Jarvis pack, the Project Intelligence pack, the Benchmarking pack, the Platform SDK package, the Event Bus, Quality Gate Engine, Evaluation Engine, Traceability Engine, Knowledge/Memory Managers, and every Platform Service (Storage, Notification, Caching, Git Integration, Speech, Document Processing). See the Repository Structure table below and `docs/process/folder_structure.md` for exactly which directories are real.

> **Note on phase numbering.** Earlier versions of this document listed "Phases 0–7" alongside a different "Phases 0–6" scheme in the Documentation Index. Both are retired. There is now one sequence: **Stages A–H**.

---

## Technology Stack (summary)

Full detail and rationale: `docs/03_architecture/platform/technology_stack.md`.

| Layer | Choice |
|---|---|
| Language / runtime | **Python 3.12**, asyncio, `mypy --strict`, Pydantic v2 |
| Packaging | **uv** workspace; each pack is its own distribution |
| Composition | Explicit composition root; **no DI container** |
| Persistence | **PostgreSQL 16** — append-only event log + materialised snapshot |
| Search | **pgvector** + Postgres FTS, hybrid RRF ranking |
| Cache / rate limiting | **Redis 7** |
| Event bus | In-process asyncio + transactional outbox (Redis Streams at a stated trigger) |
| API | **FastAPI** REST `/api/v1` + WebSocket; OpenAPI 3.1; RFC 9457 errors |
| Dashboard | **React 19 + TypeScript + Vite** |
| Model access | **LLM Gateway only** — alias-based routing, all providers behind adapters |
| Sandboxing | **Ephemeral OCI containers**, no network by default, no secrets |
| Observability | **OpenTelemetry** → OTLP; hash-chained Postgres audit log |
| Testing / CI | pytest + testcontainers + ruff + mypy; **GitHub Actions** |
| Deployment | Docker Compose (single node), Kubernetes + Helm (production) |

---

## Mandatory Reading Order

1. `README.md`
2. `PROJECT_INDEX.md` (this file)
3. `docs/00_constitution/project_constitution.md`
4. `docs/00_constitution/ai_governance_framework.md`
5. **`docs/20_glossary/glossary.md`** — the vocabulary is precise; several terms are easy to conflate
6. **`docs/18_decision_log/README.md`** — all 25 ADRs and the open decision points
7. `docs/03_architecture/platform/system_architecture.md` and `technology_stack.md`
8. **`docs/03_architecture/platform/platform_sdk.md`** — the boundary everything respects
9. `docs/02_requirements/` — functional requirements, NFRs, constraints
10. The subsystem documents relevant to your task
11. `docs/19_roadmap/implementation_roadmap.md` — what is being built now

**Do not rely on previous conversation history.**

Full index with per-document status: `docs/DOCUMENTATION_INDEX.md`.

---

## Repository Structure

**Read the Status column before exploring.** Only the **Real** rows exist in the repository. Every **Planned** row is an intended future location with **no tracked content** — git does not track empty directories, so a fresh clone will not contain them at all. A Planned directory is created by whichever implementation step first puts real content in it; until then, assume no convention and no content.

Live, more detailed version of this same table: `docs/process/folder_structure.md`.

| Folder | Status | Purpose |
|---|---|---|
| `docs/` | **Real** | Architecture, requirements, standards, ADRs — the source of truth (~150 files) |
| `kernel/` | **Real** | Platform Kernel implementation (`ai-os-kernel`) — the bulk of the working code |
| `capability_packs/` | **Real** | Installable Capability Packs. `software-engineering/` is real (5 agents, 1 workflow); `_template/` is a documented scaffold. `benchmarking/`, `project_intelligence/`, `voice_jarvis/` are planned, empty. |
| `tests/` | **Real** | `unit/` and `integration/` are real and substantial. `security/`, `performance/`, `regression/`, `benchmarks/` are planned/empty; there is no `contract/` directory yet. |
| `config/` | **Real** | Platform configuration — `platform.yaml`, `llm.yaml` |
| `infra/` | **Partial** | `docker-compose.yml` + `environments/*.yaml` are real. `kubernetes/`, `terraform/`, `docker/` are planned/empty. **There is no Dockerfile yet.** |
| `platform_sdk/` | **Real, as of Platform SDK v1.0.0 steps 1–8** | A real, installable `ai-os-sdk` package: `schemas/manifest.schema.json`, `errors/`, `models/`, `contracts/` (`Agent`/`Tool`/`LLMGateway`/`PromptRegistry`/`ToolInvoker`/`PackContextReceiver`/`ContextService`/`CapabilityPack`), and `testing/` (`pack_contract_suite` check 7). Capability Packs still import Kernel internals directly today (a documented, dated, now-waived exception in `docs/03_architecture/capability_framework/capability_pack_contract.md`) — migrating onto these real types is steps 9–14. |
| `workspace/` | **Real** | Scratch space (`scratch/`, `temp/`); prototypes are exempt from documentation-first (ADR-0003) |
| `platform_services/` | *Planned* | Shared platform services (`ai-os-services`) — Storage, Notification, Caching, Search, Indexing, Scheduling. **None built.** |
| `dashboard/` | *Planned* | Mission Control dashboard (TypeScript/React) — **no frontend project scaffolded** |
| `knowledge/` | *Planned* | Long-term engineering knowledge, patterns, memory. Structure specified in `docs/knowledge/knowledge_base_structure.md`; **zero content**. |
| `ai_context/` | *Planned* | AI Context Packs. Structure specified in `docs/ai_context/context_pack_structure.md`; **zero content**. |
| `traceability/` | *Planned* | Requirement → architecture → module → test mappings. **No Traceability Engine exists** to produce them. |
| `specs/` | *Planned* | Functional/technical specifications for generated products |
| `manifests/` | *Planned* | Machine-readable definitions |
| `governance/` | *Planned* | Governance and policy assets |
| `projects/` | *Planned* | Generated customer projects |
| `experiments/` | *Planned* | LLM benchmarking artifacts. **No Evaluation Engine or Benchmarking pack exists** to produce them. |
| `scripts/` | **Real** | `check_import_boundaries.py` — CI entry point for `pack_contract_suite` check 7 (forbidden imports), `platform_sdk_v1_scope.md` step 8 |
| `tools/` | *Planned* | Internal development tools, including the CLI. **No `aios` CLI exists** (`docs/07_api/cli_design.md` is a design spec only). |
| `assets/` | *Planned* | Images, icons, fonts |

---

## Primary Use Cases

1. **Product Creation** – Generate production-ready software from structured Markdown specifications.
2. **Existing Project Intelligence** – Understand, document, analyze, and modernize existing systems.
3. **Multi-LLM Benchmarking** – Execute identical workflows across models and compare quality, cost, speed, and process metrics with reported variance.
4. **Future Expansion** – Support additional domains through Capability Packs.

---

## Non-Negotiable Invariants

These are enforced by mechanism, not convention. Each has a governing ADR.

1. The Kernel is domain-agnostic; all domain logic lives in Capability Packs.
2. All model access — including embeddings — goes through the LLM Gateway. No pack may import a provider SDK.
3. Agents never communicate directly. The Workflow Engine is the sole orchestrator and owns all state.
4. Packs interact with the platform only through the Platform SDK.
5. Workflow control flow is declared, never planned at runtime.
6. Untrusted code executes only in a Tier 1 sandbox: no network, no secrets, no host access.
7. Authority only narrows along the invocation chain. No LLM output can grant a permission.
8. Blocking Quality Gates cannot be skipped or self-certified.
9. A Human Approval Point timeout never implies approval.
10. Secrets are referenced, never embedded, and never enter a sandbox, a prompt, or telemetry.
11. Model IDs appear only as aliases outside Gateway configuration.
12. The audit log is append-only and hash-chained.

---

## Development Rules

- Documentation is the single source of truth
- No AI model may invent requirements or architecture
- Architecture and technology decisions are recorded as ADRs before implementation
- Every feature remains modular; interfaces are preferred at real seams
- Configuration is preferred over hardcoding
- Quality gates are mandatory
- Full traceability is maintained from requirement to test
- The platform remains LLM-agnostic

---

## AI Session Checklist

1. Read `README.md` and this file
2. Read the Glossary and the Decision Log index
3. Read the relevant AI Context Pack
4. Read the relevant architecture and requirements documents
5. Check the current stage in the Implementation Roadmap
6. Review traceability for the area you are changing
7. Complete the assigned task
8. Update documentation in the same change
9. Record an ADR if a decision changed

---

## Stage Roadmap

| Stage | Name | Status |
|---|---|---|
| A | Platform Skeleton | **Process-complete, not exit-criteria-complete** — OTLP export and the Compose observability profile remain |
| B | Minimum Viable Kernel | **In Progress** — Workflow Engine core, LLM Gateway, Prompt Engine, Context Manager, Capability Manager all have real slices. Event Bus, Quality Gate Engine, Tool Invoker, and the Platform SDK package are the outstanding blockers. |
| C | First Capability Pack (thin slice) | **Partially landed early** — a real 5-agent Software Engineering pack and a real Tier 1 `DockerSandbox` exist, ahead of Stage B's completion. Quality gates, human approval, and the audit chain remain. |
| D | Evaluation & Multi-LLM Experimentation | Not started (a second provider adapter exists early; Evaluation Engine is 0%) |
| E | Project Intelligence | Not started |
| F | Dashboard, Voice, Notifications | Not started |
| G | Hardening & Production Readiness | Not started |
| H | Expansion | Not started |

Detail and exit criteria: `docs/19_roadmap/implementation_roadmap.md`. Per-module percentages: `docs/19_roadmap/feature_inventory.md`.

> **Why stages overlap.** A product-owner reprioritization (2026-07-27) redirected work toward the shortest real path to a working multi-agent pipeline, which pulled some Stage C deliverables ahead of Stage B completion. This is deliberate and recorded — see `docs/19_roadmap/history/INDEX.md`. Do not assume stages complete strictly in order.

---

## Process and Working Rules (for any session, human or AI)

The architecture documents describe *what* to build. These describe *how work proceeds* here:

| Document | Purpose |
|---|---|
| `CLAUDE.md` | Root-level session entry point: core process rule, approval workflow, known environment quirks |
| `docs/process/files_to_read_first.md` | What to read, and when, for a given task |
| `docs/process/standing_rules.md` | Approval/scope/documentation/git discipline |
| `docs/process/reporting_format.md` | The expected shape of a step's completion report |
| `docs/process/coding_standards.md` | The load-bearing subset of `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` |
| `docs/process/folder_structure.md` | What actually has real content on disk vs. what is only planned |

---

## Maintenance

Update this document whenever the stage changes, a stage completes, the repository structure changes, a major architectural decision is approved, priorities change, or a new Capability Pack is introduced.

Specifically: the **Current Status**, **Repository Structure** Status column, and **Stage Roadmap** table above are the three parts most likely to go stale. When a Planned directory gains real content, or a stage's status changes, update them here *and* in `docs/process/folder_structure.md` and `docs/19_roadmap/feature_inventory.md` in the same step.
