# Implementation Status – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Implementation Status
**Version:** 2.0 (restructured short form)
**Status:** Active
**Last Updated:** 2026-07-28 (deleted the stale `capability_packs/analytics/` folder; resolved the `sys.executable` portability gap and wired `DockerSandbox` in as the Software Engineering pack's real default sandbox backend, `LocalSubprocessSandbox` remaining explicitly selectable. See `history/023_docker_sandbox_default_wiring.md`.)

---

## 1. Purpose

A living record of what has actually been built, checked against the exit criteria in `implementation_roadmap.md`, so any session (human or AI) can resume work without rescanning the repository or relying on chat history.

This document is deliberately **short** — current stage, what exists, current blockers, and the next recommended step only. Full chronological detail, subsystem by subsystem, lives in `docs/19_roadmap/history/` (see `history/INDEX.md`). For the complete, granular, per-module completion tracker (every feature/module/phase with a percentage and status), see `docs/19_roadmap/feature_inventory.md` — that document, not this one, is the authority on "what % done is X." This document is descriptive, not authoritative — on any conflict, the Implementation Roadmap and the ADRs govern.

**Read this file first, every session, before anything else** (see `CLAUDE.md`). Read a `history/` file only when the current task specifically needs that subsystem's detail.

---

## 2. Current Stage

**Stage A – Platform Skeleton** is process-complete but not exit-criteria-complete (see §4). **Stage B – Minimum Viable Kernel** is underway and has reached a real, demonstrable milestone: a complete four-agent software-engineering delivery pipeline (Architecture → Build → Test → Documentation) runs end to end through the real Workflow Engine, now through **`DockerSandbox` as the genuine default Tier 1 sandbox backend** (config-driven via `AIOS_SANDBOX_BACKEND`, `LocalSubprocessSandbox` remaining explicitly selectable) — the last real safety gap on this pipeline is closed.

As of this step: **625 unit tests passing** (kernel + Software Engineering pack), **229 integration tests collected, 0 failed** (all 229 skipped this session — Docker Desktop unavailable; see §4). `mypy --strict` (280 source files) and `ruff` clean throughout. The new, Docker-gated end-to-end proof (`tests/integration/sandbox/test_delivery_pipeline_docker.py`) has not yet executed for real this session — the single highest-priority re-verification item once Docker Desktop is available.

Two prior steps (2026-07-28) were documentation-only: an infrastructure/history-split step, then a full feature/module/phase inventory (`docs/19_roadmap/feature_inventory.md`). This step returns to feature development.

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
- **Software Engineering Capability Pack**: Architecture, Build, Test, and Documentation agents, all real, chained into one declared workflow (`se.delivery_pipeline`) via `WorkflowStepOutputResolver`, now defaulting to `DockerSandbox`. → `history/015`–`019`, `023`.
- **Documentation reconciliation**: agent-catalog naming fixed (`architecture`/`qa-test`/`build`), doc-drift closed, shared Postgres test fixture (`tests/integration/_postgres_fixture.py`) skips cleanly without Docker. → `history/021`.
- **Feature/module/phase inventory**: tracked, weighted completion table (44 modules, ≈20% overall at the time) — see `docs/19_roadmap/feature_inventory.md`. Update that document's own table at the end of every future step.
- **This step**: `capability_packs/analytics/` (stale, undocumented) deleted; `DockerSandbox` wired in as the SE pack's real default sandbox; a new real, Docker-gated end-to-end pipeline test proves network isolation and filesystem containment during an actual generated-code run. → `history/023`.

---

## 4. Current Blockers

Full detail (every gap, every reasoning) is preserved verbatim in `history/022_gap_analysis_and_blockers_snapshot.md`. The load-bearing ones, distilled:

- **The new Docker-gated end-to-end pipeline test has not yet executed for real** — Docker Desktop was unavailable this session (see below); re-running it (and every other Docker/Postgres-gated integration test) is the single highest-priority re-verification item once it's available.
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

The `DockerSandbox`-wiring recommendation from the previous two steps is now done. Recommendation: **re-run the full test suite (unit + integration, including the new `test_delivery_pipeline_docker.py`) once Docker Desktop is available**, to convert this step's "collects and skips cleanly" verification into a real, executed pass — the identical pattern this project has followed every time a step landed while Docker was unavailable. If Docker is available at the start of the next session, do this first, before starting any new feature work. If a new feature step is preferred instead, the next-largest gap per `feature_inventory.md` is Phase C's remaining Software Engineering agents (12 of 16 still unbuilt) or Phase D's Evaluation Engine (schema-only, 0% engine code).

---

## 7. Maintenance

Update this document at the end of every implementation step: refresh §2 (current stage) and §4 (blockers), re-state §6 with the next recommended step, and commit. If a step's own detail is large enough to warrant its own history entry, add a new numbered file to `docs/19_roadmap/history/` and a line to `history/INDEX.md` — do not let this document grow long again (see the big-file convention in `CLAUDE.md`).

**Also update `docs/19_roadmap/feature_inventory.md`'s own completion table (Section 5) and overall weighted percentage (Section 6) at the end of every step** — standing rule recorded 2026-07-28 in `CLAUDE.md` / `docs/process/standing_rules.md`.
