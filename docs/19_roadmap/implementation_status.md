# Implementation Status – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Implementation Status
**Version:** 2.0 (restructured short form)
**Status:** Active
**Last Updated:** 2026-07-28 (documentation consolidation audit — 100 files, docs/structure only, no code behaviour changed. Corrected badly stale stage status in `PROJECT_INDEX.md`/`README.md`/`implementation_roadmap.md`; added honest Implementation Status sections to 82 documents; annotated all 25 ADRs append-only; discovered that ~70 documented directories have zero tracked files and are absent from a fresh clone; removed the dead `capability_packs/software_engineering/` duplicate. See `history/025_documentation_consolidation_audit.md`.)

---

## 1. Purpose

A living record of what has actually been built, checked against the exit criteria in `implementation_roadmap.md`, so any session (human or AI) can resume work without rescanning the repository or relying on chat history.

This document is deliberately **short** — current stage, what exists, current blockers, and the next recommended step only. Full chronological detail, subsystem by subsystem, lives in `docs/19_roadmap/history/` (see `history/INDEX.md`). For the complete, granular, per-module completion tracker (every feature/module/phase with a percentage and status), see `docs/19_roadmap/feature_inventory.md` — that document, not this one, is the authority on "what % done is X." This document is descriptive, not authoritative — on any conflict, the Implementation Roadmap and the ADRs govern.

**Read this file first, every session, before anything else** (see `CLAUDE.md`). Read a `history/` file only when the current task specifically needs that subsystem's detail.

---

## 2. Current Stage

**Stage A – Platform Skeleton** is process-complete but not exit-criteria-complete (see §4). **Stage B – Minimum Viable Kernel** is underway and has reached a real, demonstrable, **now genuinely Docker-verified** milestone: a complete four-agent software-engineering delivery pipeline (Architecture → Build → Test → Documentation) runs end to end through the real Workflow Engine and **`DockerSandbox` as the genuine default Tier 1 sandbox backend**, proven for real against a live daemon — including a real proof that network isolation and filesystem containment hold for code the pipeline itself generated and ran, not just in an isolated guarantee check. A fifth agent, Requirements Analyst, is built and proven independently (not yet chained into the pipeline).

As of this step: **849 tests passed** (unit + integration + pack, combined), **11 skipped** (opt-in-live, no API key — expected), **0 failed**. `mypy --strict` (283 source files) and `ruff` clean throughout. This is the first genuinely real-Docker-verified pass of the entire integration suite since `DockerSandbox` became the default.

Three prior steps (2026-07-28) were documentation/infrastructure-only. This step is real feature development plus real-environment verification.

---

## 3. What Exists Now (compact)

- **Persistence & Workflow Engine core**: Postgres schema + Alembic migrations for `workflow_instances`/`workflow_events`/`workflow_leases`/`workflow_steps`/`approvals`; definition loading/validation; instance creation, state transitions, multi-step progression to completion; lease acquire/renew/release/reap; single-shot and run-to-completion composition; `list_steps`/`list_events` read accessors. → `history/002`, `003`.
- **Cross-cutting infra**: CI aligned with the real codebase; minimal Secrets Resolution (`EnvSecretProvider`, ADR-0024); real OpenTelemetry spans + one metric (console exporters). → `history/004`.
- **Catalog & evaluation schema**: all 6 `catalog` tables and all 6 `evaluation` tables exist, with FKs retrofitted per `data_model.md`. → `history/005`.
- **LLM Gateway**: `AnthropicAdapter` + `LocalAdapter`, `Router`/`DispatchingLLMGateway`, Retry & Fallback (Circuit Breaker, Backoff, Error Taxonomy), two independent budget ceilings (alias + workflow), `TraceContext`, Capability Negotiator matrix. Only `anthropic` registered by default. → `history/006`, `011`.
- **Prompt Engine**: Protocol + `InMemoryPromptEngine`/`SqlPromptCatalog`, `PromptedCompletionService`. No version resolution/Resolver/caching yet. → `history/006`.
- **Agent/Tool registries**: `AgentRegistry`/`ToolRegistry`, both in-memory and SQL-backed (`SqlAgentRegistry`/`SqlToolRegistry` resolve real catalog rows, gated on pack activation, via `EntrypointLoader`). → `history/007`.
- **Capability Manager**: minimal pack lifecycle (register/activate/deactivate), no discovery/upgrades/health/permissions yet. → `history/008`, `010`.
- **Security Manager**: bearer-token JWT auth, 4 permissions, fronting 9 HTTP routes — all narrower than their documented contracts. Not OIDC. → `history/009`.
- **Context Manager**: `WorkflowStateResolver` + `WorkflowStepOutputResolver`, Size & Token Budget Enforcer. 1 of 6 documented sources built. → `history/012`.
- **Retrieval**: `knowledge.documents`/`chunks` writer + keyword-search reader. No vector/hybrid search, no consumer yet. → `history/013`.
- **Sandbox & Tool execution**: `LocalSubprocessSandbox` (3/5 guarantees) and `DockerSandbox` (5/5, ADR-0016 Tier 1, proven live) both implement `SandboxExecutor`, each now declaring its own `python_command`; `SandboxedCommandTool` + `ToolStepExecutor` dispatch; `ai_os_kernel.sandbox.default_executor` resolves the real default from `AIOS_SANDBOX_BACKEND` (`"docker"` unless set to `"local"`). → `history/014`, `020`, `023`.
- **Software Engineering Capability Pack**: 5 real agents — Architecture, Build, Test, and Documentation chained into one declared workflow (`se.delivery_pipeline`) via `WorkflowStepOutputResolver`, defaulting to `DockerSandbox`; Requirements Analyst proven independently, not yet chained in. → `history/015`–`019`, `023`, `024`.
- **Documentation reconciliation**: agent-catalog naming fixed (`architecture`/`qa-test`/`build`), doc-drift closed, shared Postgres test fixture (`tests/integration/_postgres_fixture.py`) skips cleanly without Docker. → `history/021`.
- **Feature/module/phase inventory**: tracked, weighted completion table — see `docs/19_roadmap/feature_inventory.md`. Update that document's own table at the end of every future step.
- **Prior step**: `capability_packs/analytics/` (stale, undocumented) deleted; `DockerSandbox` wired in as the SE pack's real default sandbox. → `history/023`.
- **Prior step**: the full integration suite (incl. the Docker-gated pipeline test) ran for real and passed; two real bugs found and fixed (a `python_command` mismatch, a hardcoded `sys.executable` in a test); Requirements Analyst Agent built. → `history/024`.
- **This step**: documentation consolidation audit — the docs are now self-sufficient for a zero-context LLM. 82 documents carry honest Implementation Status sections; stage status corrected everywhere; all 25 ADRs annotated; every TBD resolved; the dead `capability_packs/software_engineering/` duplicate removed. → `history/025`.

**Reading the architecture docs correctly (important, new this step):** AI_OS is documentation-first, so most `docs/03_architecture/` documents were written before their code and many describe subsystems that are 0% built. **Every one now carries an `## Implementation Status` section near the top — read it before assuming the document describes callable code.** `docs/DOCUMENTATION_INDEX.md` §2a enumerates the entirely-unbuilt set. `docs/process/folder_structure.md` is definitive on which directories actually exist (git tracks no empty directories, so most "planned" folders are absent from a fresh clone).

---

## 4. Current Blockers

Full detail (every gap, every reasoning) is preserved verbatim in `history/022_gap_analysis_and_blockers_snapshot.md`. The load-bearing ones, distilled:

- **Requirements Analyst is proven but not chained into `se.delivery_pipeline`** — the pipeline still starts at Architecture; wiring Requirements Analyst in as its own first step is a distinct, later increment (would need `delivery_pipeline.yaml`/`pipeline.py`'s own `_STEP_SOURCES` updated, plus re-verification of the existing chained tests).
- **Only one LLM provider (`anthropic`) is registered by default**; `LocalAdapter`/cross-provider fallback exist but are commented out in checked-in config.
- **Security Manager is pre-shared-secret JWT, not real OIDC** — not production-credible as-is.
- **No pack discovery, upgrade path, health monitoring, or permissions enforcement** in the Capability Manager.
- **`approvals` table has no writer** — no Human Approval Point execution path exists yet.
- **No multi-instance worker loop** — `run_to_completion`/`reap_once` exist for one instance/one bounded pass; nothing yet schedules either across many instances.
- **Context Manager has only 1 of 6 documented sources** (Knowledge/Memory/AI Context Packs/Runtime Config resolvers don't exist); no Filter/Ranker, no Context Audit Logger persistence.
- **No GitHub remote configured** for this repository (see §5) — `gh` CLI unavailable in this environment; a manual step is needed.
- **Docker Desktop availability is intermittent across sessions** in this development environment — see `CLAUDE.md`.

---

## 5. Git / Repository Status

This is now a git repository (`git init` this step), branch `main`, with one baseline commit capturing all work through the naming-reconciliation step. **No GitHub remote exists** — the `gh` CLI is unavailable in this environment, so pushing to GitHub requires a manual step from the product owner (create a remote repository, then `git remote add origin <url> && git push -u origin main`). The repository is otherwise ready to push as-is.

Per standing rule (`docs/process/standing_rules.md`), every step from now on ends with a commit; the hash is reported at the end of each step's report.

---

## 6. Recommended Next Small Step

The documentation consolidation audit is done. Recommendation: **wire the Requirements Analyst Agent into `se.delivery_pipeline` as its own first step** — extending the real hand-off chain from four steps to five (`requirements-analyst` → `architecture` → `build` → `qa-test` → `documentation`), so the pipeline starts from a raw requirement rather than one already shaped as a design brief.

Preferred over building a sixth agent (`code-reviewer`) because it converts an already-built-but-unused agent into delivered value, exercises the existing `WorkflowStepOutputResolver` hand-off once more without inventing any mechanism, and keeps the pack's breadth honest — five agents of which five are used, rather than six of which four are.

Concretely: add the step to `capability_packs/software-engineering/workflows/delivery_pipeline.yaml`, extend `pipeline.py`'s `_STEP_SOURCES`/`_FIELD_SELECTORS` for the new first hand-off, move `_StepScopedResolver`'s `WorkflowStateResolver` scope from `architecture` to `requirements-analyst`, and re-verify both delivery-pipeline integration tests (deterministic and Docker-gated).

A separate, small follow-up worth scheduling: complete the ~20 documents this audit did not line-by-line audit (listed in `history/025_documentation_consolidation_audit.md`'s "honest note on completeness"). None is misleading today, but each still lacks its own Implementation Status and Related Documents sections.

---

## 7. Maintenance

Update this document at the end of every implementation step: refresh §2 (current stage) and §4 (blockers), re-state §6 with the next recommended step, and commit. If a step's own detail is large enough to warrant its own history entry, add a new numbered file to `docs/19_roadmap/history/` and a line to `history/INDEX.md` — do not let this document grow long again (see the big-file convention in `CLAUDE.md`).

**Also update `docs/19_roadmap/feature_inventory.md`'s own completion table (Section 5) and overall weighted percentage (Section 6) at the end of every step** — standing rule recorded 2026-07-28 in `CLAUDE.md` / `docs/process/standing_rules.md`.
