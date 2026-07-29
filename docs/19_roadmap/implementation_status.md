# Implementation Status – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Implementation Status
**Version:** 2.0 (restructured short form)
**Status:** Active
**Last Updated:** 2026-07-28 (Platform SDK v1.0.0 build started: Step 1 of 15 complete — `platform_sdk/` scaffolded as a real, installable `ai-os-sdk` distribution, packaging only, no Protocols/models/errors yet. See §2 and §6. Prior entries: the SDK build was scoped as its own plan document (`../03_architecture/platform/platform_sdk_v1_scope.md`); before that, a targeted fix step corrected stale test/mypy numbers in §2 below and closed 15 real mypy errors with a `py.typed` marker; before that, the product-owner decision recorded **the direct-Kernel-import exception is now a hard gate — no new agent or Capability Pack may be added until the Platform SDK exists**. See §4 and `history/026_platform_sdk_gate_and_audit_completion.md`.)

---

## 1. Purpose

A living record of what has actually been built, checked against the exit criteria in `implementation_roadmap.md`, so any session (human or AI) can resume work without rescanning the repository or relying on chat history.

This document is deliberately **short** — current stage, what exists, current blockers, and the next recommended step only. Full chronological detail, subsystem by subsystem, lives in `docs/19_roadmap/history/` (see `history/INDEX.md`). For the complete, granular, per-module completion tracker (every feature/module/phase with a percentage and status), see `docs/19_roadmap/feature_inventory.md` — that document, not this one, is the authority on "what % done is X." This document is descriptive, not authoritative — on any conflict, the Implementation Roadmap and the ADRs govern.

**Read this file first, every session, before anything else** (see `CLAUDE.md`). Read a `history/` file only when the current task specifically needs that subsystem's detail.

---

## 2. Current Stage

**Stage A – Platform Skeleton** is process-complete but not exit-criteria-complete (see §4). **Stage B – Minimum Viable Kernel** is underway and has reached a real, demonstrable, **now genuinely Docker-verified** milestone: a complete four-agent software-engineering delivery pipeline (Architecture → Build → Test → Documentation) runs end to end through the real Workflow Engine and **`DockerSandbox` as the genuine default Tier 1 sandbox backend**, proven for real against a live daemon — including a real proof that network isolation and filesystem containment hold for code the pipeline itself generated and ran, not just in an isolated guarantee check. A fifth agent, Requirements Analyst, is built and proven independently (not yet chained into the pipeline).

**Numbers current as of 2026-07-28 (re-verified fresh, not carried forward from an earlier step — see the lesson recorded in `docs/process/standing_rules.md` about exactly this failure mode):** `pytest -q` (full suite, unit + integration + pack, Docker available) → **803 passed, 11 skipped** (all 11 are the same opt-in-live-provider suite, no API key set — expected per ADR-0015), **0 failed**. `mypy --strict kernel/src kernel/alembic tests` (the exact scope CI runs) → **0 errors, 267 source files checked**, clean. `ruff check .` → clean. This is the first genuinely real-Docker-verified pass of the entire integration suite since `DockerSandbox` became the default.

A prior version of this paragraph claimed "849 tests passed" and "mypy --strict (283 source files) clean" — both were stale by the time a hard-evidence audit re-ran them fresh and found 803/803 passing but **15 real mypy errors** (root cause: `capability_packs/software-engineering` shipped with no `py.typed` marker, so mypy treated cross-boundary imports from `tests/` into the pack as untyped). Fixed this step by adding the marker; see `history/026_platform_sdk_gate_and_audit_completion.md`'s successor step for the full before/after. The "283 files" figure was real once, under a *different* mypy invocation that additionally passes `capability_packs/software-engineering/src` and its `tests/` directory on the command line (matching `[tool.mypy].files` in `pyproject.toml` exactly) — CI itself runs the narrower `kernel/src kernel/alembic tests` invocation quoted above, which is what these numbers now reflect.

Three prior steps (2026-07-28) were documentation/infrastructure-only. The step recorded above this paragraph closed the documentation audit and recorded a hard product-owner gate (see §4, first item) — no code changed. This paragraph itself was corrected by a small, targeted follow-up fix step (also 2026-07-28) that touched only: the `py.typed` marker, this paragraph's numbers, a new standing-rules lesson, and two documentation-formatting fixes.

**Platform SDK build: the sequence was revised from 15 to 18 steps after an independent architecture review (2026-07-29), and Steps 1–2 are complete.** The review found 7 real problems in the original plan, three of them blocking — most importantly that no step made the Kernel able to *supply* the Protocols the pack would be migrated onto, and that the injection path (`EntrypointLoader` hardcodes `cls()`; `PackContext` is identity-only) was listed as a non-goal. All findings accepted; three new steps (**2a** Protocol/reality reconciliation, **6a** Kernel-side adapters, **6b** `PackContext` construction + injection) were inserted, `SecretResolver` was dropped, migration order reversed to `qa-test`-first, and `pipeline.py` relocation became step 7. Full findings and reasoning: `../03_architecture/platform/platform_sdk_v1_scope.md` §6a.

- **Step 1 (done):** `platform_sdk/` is a real, installable PEP 621 distribution (`ai-os-sdk`), a workspace member; `import ai_os_sdk` works.
- **Step 2 (done):** `ai_os_sdk.errors` holds the real `ErrorCategory` (all 6 documented categories), `StructuredError`, and the `AiOsError` hierarchy with its six subclasses, each mapping 1:1 onto a `StructuredError`. `ai_os_sdk.models` holds `ArtifactRef`, the canonical §4.1 `TraceContext`, `SecurityContext`, and `StepBudget`. **Consumed by nothing; no existing code changed.** Note: this creates the *third* `TraceContext` in the repository — `ai_os_kernel.observability.trace` and `ai_os_kernel.llm_gateway.models` each hold a narrower one, and both of their docstrings already name §4.1 as the canonical shape they reduce. Consolidating them is Kernel-side work for step 2a/6a, not step 2.
- **No Protocol exists yet**, deliberately: step 2a must decide the real Protocol shapes before step 3 writes any, because the specified `Agent`/`Tool` shapes are incompatible with `SqlAgentRegistry`'s `isinstance` gate (`registry.py:222`).

Verified fresh after step 2: `pytest -q` (root suite) → **803 passed, 11 skipped, 0 failed** (unchanged); `pytest -q capability_packs/software-engineering/tests/` → **46 passed** (unchanged); `pytest -q platform_sdk/tests/` → **65 passed**; `mypy --strict` over the full configured scope → **0 errors, 295 source files**; `ruff check .` and `ruff format --check .` → clean.

> **🛑 HARD GATE (product-owner decision, 2026-07-28) still in force: no new agent or Capability Pack until the Platform SDK exists *and* the Software Engineering pack is migrated onto it and verified compliant (`platform_sdk_v1_scope.md` step 15).** Step 1 (scaffolding) does not lift this gate on its own — see §4 for the full statement and §6 for what's next.

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

- **🛑 HARD GATE, recorded 2026-07-28 (product-owner decision): the direct-Kernel-import exception documented in `docs/03_architecture/capability_framework/capability_pack_contract.md`'s Platform Interaction Rules is now a hard blocker on further pack growth, not a soft "temporary" note.** No new agent may be added to any Capability Pack, and no new Capability Pack may be added, **until a real Platform SDK package (`ai-os-sdk`) exists.** The five existing Software Engineering pack agents (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) are grandfathered as-is and need no change — this gate blocks only the *next* addition. Recorded in three places: `capability_pack_contract.md` (the gate itself), `feature_inventory.md` module 27 (tracked as the blocking item), and `docs/process/standing_rules.md` (the standing rule preventing a future step from accidentally violating it). **The Platform SDK build is not started by this step** — it is explicitly scoped as its own dedicated future step (see §6).
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

**Step 2a of 18 — the Protocol/reality reconciliation decision. Docs only; recommended as its own focused step with no code.** For each of `LLMGateway`, `PromptRegistry`, `ToolInvoker`, `Agent`, and `Tool`, decide *narrow-the-spec* vs *extend-the-Kernel*, and amend `platform_sdk.md` §4.2/§4.3/§5.1/§5.2/§5.6 to match. **This must land before Step 3 writes any Protocol**, because the currently-specified shapes cannot be satisfied by any real Kernel object:

- `LLMGateway` (§5.1) specifies 5 methods; `DispatchingLLMGateway` has 2 (`complete`, `capabilities`).
- `PromptRegistry` (§5.2) specifies `render(prompt_id, variables, version)` + `get(...)`; the real `PromptEngine` is `render(request)` with no `get()`.
- `ToolInvoker` (§5.6) has no counterpart at all.
- `Agent`/`Tool` (§4.2/§4.3) are outright incompatible with the Workflow Engine's real calling convention — an SDK-shaped agent would fail `SqlAgentRegistry`'s `isinstance` check (`registry.py:222`) and `AgentStepExecutor`'s `output_schema` validation, and the SDK `Tool` method is even named differently (`invoke` vs `execute`).

Full 18-step sequence, current position: **Steps 1–2 done.** Then 2a → 3 → 4 → 5 → 6 → 6a → 6b → 7 → 8 (SDK build + Kernel adapters + injection path + check 7) → 9–14 (migration, `qa-test` first) → 15 (compliance completion, and only then does the growth gate lift). See `../03_architecture/platform/platform_sdk_v1_scope.md`; each step is individually approved before it starts.

A separate, smaller, non-blocking follow-up: the prior step completed the full documentation audit (see §7 and `history/026`), so there is no remaining doc-completeness debt to schedule.

---

## 7. Maintenance

Update this document at the end of every implementation step: refresh §2 (current stage) and §4 (blockers), re-state §6 with the next recommended step, and commit. If a step's own detail is large enough to warrant its own history entry, add a new numbered file to `docs/19_roadmap/history/` and a line to `history/INDEX.md` — do not let this document grow long again (see the big-file convention in `CLAUDE.md`).

**Also update `docs/19_roadmap/feature_inventory.md`'s own completion table (Section 5) and overall weighted percentage (Section 6) at the end of every step** — standing rule recorded 2026-07-28 in `CLAUDE.md` / `docs/process/standing_rules.md`.
