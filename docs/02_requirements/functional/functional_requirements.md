# Functional Requirements – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Functional Requirements
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines what AI_OS must do. It is the **root of the traceability chain** required by the Constitution: every architecture element, module, and test traces back to a requirement here.

Requirement IDs are stable and permanent (`FR-###`). A requirement is never renumbered; it is superseded and marked so.

Each requirement states a capability and its acceptance criterion. Non-functional targets live in `../non_functional/nfr.md`; constraints in `../constraints/constraints.md`.

---

## Implementation Status (2026-07-31; counts resynced 2026-08-08; **false "not built" claims corrected 2026-08-11**)

This document is **approved requirements**, not a description of built software.

> **Authority note (2026-08-11).** For "is FR-### done?", **`../../19_roadmap/feature_inventory.md` is the authority** — it is updated every step and derived from direct source inspection. This section is a periodically-resynced summary and *will* lag it. Where the two disagree, `feature_inventory.md` wins. `../../19_roadmap/STATUS.md` and `MODULE_BOARD.md` are the authority for *ticket* completion (they are generated from the tickets themselves); this document is the authority only for **scope and acceptance criteria**.

**All 75 FRs are classified below.** Counts: **60 MUST** (v1), **14 SHOULD** (v1 if capacity allows), **1 LATER** (FR-044, post-v1).

**The aggregate built/partial/untouched split previously stated here (7/24/29 of 60 MUST) is withdrawn, not restated.** A full-project audit on 2026-08-11 verified that this section still called five things "not built" that are demonstrably real in current code (FR-014, FR-030, all of §5, all of §6, and the Traceability Engine/`trace.links` — each corrected below with the file and line that disproves the old claim). Recomputing an honest aggregate would require re-verifying all 60 MUST FRs individually, which that audit did not do; publishing a new number without that work would be a fabricated count. So no aggregate is given here — use `feature_inventory.md`'s per-module completion table instead. The original 2026-07-31 baseline decision (5/19/36, accepted by the product owner as the real v1 backlog starting point, R-006) is unaffected; only the summary counts derived from it are withdrawn.

**Built (fully or as a working slice):** FR-001 (manifest validation, fail-closed), FR-004/FR-005 (declared workflow graph executes; append-only event log + snapshot in one transaction), FR-007 (all model calls go through the LLM Gateway), FR-021 (Tier 1 sandbox — `DockerSandbox` is the config-driven default and has been verified live: no network, no host filesystem access, for code the pipeline itself generated), **FR-039** (corrected 2026-08-08 — the `code-review` agent, not `lint`, is the real answer: `CodeReviewerAgentOutput` carries `file`/`line`/`severity`/`confidence` per finding, exactly this FR's own acceptance criterion, `P03-S02-M29-T07`), **FR-110** (corrected 2026-08-08 — a real, hash-chained audit log: `SqlAuditLogWriter` computes the chain under a real advisory lock, `verify_chain()` is real, and a scheduled verification job runs inside `_lifespan`; `R-009` closed 2026-08-01), **FR-030** (corrected 2026-08-11 — a real Markdown specification parser and a real declared `specification` workflow input; see the corrections table below), **FR-071** (corrected 2026-08-11 — per-run model pinning means the same definition genuinely runs against each declared model with only that dimension varied; see the corrections table below).

**Partially built:** FR-002/FR-003 (register/activate/deactivate, plus real startup discovery, a manifest→catalog installer, and health polling — no upgrade path, no permissions enforcement), FR-006 (leases acquire/renew/release/reap exist and are continuously reaped; no multi-instance worker loop schedules them), FR-008 (retry/fallback/circuit-breaker code is real but only the `anthropic` provider is registered by default), FR-009 (spans + `evaluation` tables exist; not every field is populated), FR-010 (2 of 6 documented context sources), FR-011 (render + validate, no version resolver), FR-015/FR-016/FR-017 (minimal slices — `Ready` path plus a critical database check; 3 of 7 config layers; `env` secret backend only), FR-022 (2 of 5 budget checks), **FR-012 (updated 2026-07-31 — no longer "not built": a real, blocking `QualityGateStepExecutor` halts `se.delivery_pipeline` on a failing gate, across two real gate categories, with bounded retry and a real `evaluation.gate_results` writer. The full engine — Gate Registry, pack-declared gates, Result Evaluator, Policy Enforcer — remains unbuilt)**, **FR-014**/**FR-116** and all of **§5**/**§6** except FR-071/FR-078 (all corrected 2026-08-11 — see the corrections table below for the evidence on each), **FR-112** (knowledge writer and keyword-search reader are real; no indexing, query engine, or provenance/versioning component), **FR-113** (spans, `structlog` and one real metric are correlated end to end; console exporters only — no OTLP, no Collector), **FR-018** (corrected 2026-08-08 — `over_permitted_permissions`/`narrow_permissions` genuinely bound principal→workflow→agent→tool in `SqlAgentRegistry`'s own real resolution path, proven by a full four-hop chain test; enforced only when a caller supplies `principal_permissions` — every caller that omits it, which is most callers before `P03-S05-M14-T09`'s own real HTTP route, remains unenforced, so "end-to-end" is not yet universal), **FR-013** (corrected 2026-08-08 — `HumanApprovalStepExecutor` genuinely, durably pauses a real instance and resumes only on a real, attributable, RBAC-authorized decision, proven via real Postgres and real HTTP; updated 2026-08-12, `P02-S07-M17-T05`: a real notification now reaches a real channel when an approval is requested or decided, closing this entry's own "a Notification Service for its own declared channels" gap for the single configured webhook channel — Dashboard/email/Voice adapters and per-approver routing remain unbuilt, as does the automatic timeout sweep), **FR-111** (corrected 2026-08-08 — the same real mechanism gates three concrete governance points today, `approve-git-push`/`approve-requirements`/`approve-architecture`; no canonical, enumerated "governance decision set" registry exists yet, so coverage is per-workflow, not systematic), **FR-019** (corrected 2026-08-08 — a real link writer plus real, correct impact and coverage queries against real Postgres, matching this FR's own acceptance criterion directly; no Agent/Workflow anywhere calls them in a real running instance yet), **FR-020** (corrected 2026-08-08 — `SqlRunManifestRecorder` really records every real step's resolved provider/model/pack per run, wired into every real workflow composition; the "re-launchable from it" half of this FR's own acceptance criterion, and FR-114's replay, remain unbuilt). In the Software Engineering pack: FR-031, FR-032, FR-034, FR-038 and FR-041 each have one real agent behind them (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`), plus a sixth, `lint`, added 2026-07-30, and a seventh, `code-review` — now the real FR-039 agent, see Built above.

### Corrections applied 2026-08-11 (full-project audit)

The audit verified six claims in this section against current source and found each of them **false**. Each is corrected above; the evidence that disproved the old claim is recorded here so the correction is checkable, not merely asserted. (A seventh correction, to §9.1's Traceability claim, is recorded in that section.)

| Old claim in this section | Verdict | Evidence in current code |
|---|---|---|
| FR-014 "no Event Bus; only the `platform.event_outbox` table exists" | **False** | `ai_os_kernel/event_bus/` is 5 real modules: `InProcessEventBus` (`bus.py:98`, bounded per-subscriber queues, typed/versioned `Event`), an `EventBus` Protocol, and a real `OutboxRelay` (`outbox_relay.py:82`) with `run_outbox_relay_loop`. It is constructed in the real composition root (`bootstrap.py`, `app.state.event_bus`) and closed on shutdown. It now has **real production publishers and subscribers**: `evaluation_engine/cost_anomaly.py:175` publishes; `notification/service.py:124` and `routes/stream.py:201` (the live WebSocket) subscribe. → **partially built**. *Updated 2026-08-12 (`P02-S07-M17-T04`):* two of that list's four gaps are now closed — `platform.event_outbox` has a real writer (`event_bus/outbox_writer.py`, joining the caller's transaction so ADR-0012's same-transaction requirement is structural) and the Workflow Engine does emit, for its terminal `workflow.completed` only. *Updated again 2026-08-12 (`P02-S07-M17-T05`):* `approval.requested`/`approval.decided` now have a real producer as well. Still genuinely missing: any Capability-Manager/Quality-Gate emission, a `workflow.failed` event (nothing ever persists an instance as `failed`), the Topic/Channel Manager, the Schema Registry, and a bounded relay-retry policy. |
| FR-030 "No Markdown parsing and no requirement-item extraction exists. **FR-030 is not built.**" | **False** | `parse_markdown_specification(text) -> list[str]` plus `SpecificationParseError` in `capability_packs/software-engineering/src/ai_os_pack_software_engineering/workflows/spec_parser.py:41,48`; `specification` is a real declared workflow input (`delivery_pipeline.yaml:179`), additive alongside the still-required `requirement`; ticket `P03-S03-M30-T02` is `done`. → **built as a working slice.** |
| "all of §5 (FR-050–FR-059, Project Intelligence)" not built | **False** | `capability_packs/project_intelligence/` is ~2,530 real lines with a schema-valid `manifest.yaml` declaring five real Tools — `repository.ingest`, `language.detect`, `dependency.graph`, `architecture.recover`, `documentation.generate` — which the real Manifest Loader discovers and `SqlToolRegistry` resolves. Tickets `P05-S02-M32-T01`–`T06` are `partial`, `T07` `done`. → **partially built**, not untouched. |
| "all of §6 (FR-070–FR-078, benchmarking)" not built | **False** | Seven of the nine have real code: FR-070 (`evaluation_engine/experiment_repository.py`), FR-071 (per-run model pinning — `experiment_run_orchestrator.pin_definition_to_model`, so the same definition genuinely runs against each declared model with only that dimension varied), FR-072 (`replicate_management.py`), FR-073 (`metrics_collector.py`), FR-074/FR-075 (`comparison_computer.py`), FR-076 (`cost_ceiling.py`), FR-077 (`prompt_adaptation.py`). The full define→run→compare loop is reachable over HTTP (§6.3 of `../../07_api/api_architecture.md`). Only **FR-078** (historical trend view) is genuinely unbuilt. |
| FR-116 "no Notification Service" | **False** | `NotificationService` (`notification/service.py:108`) with a `DeliveryChannel` Protocol and a real `WebhookChannel` (`webhook.py:20`), plus `SqlNotificationDeliveryRecorder`, constructed in `bootstrap.py` whenever `notification_webhook_url` is configured. → **partially built** (webhook only; no other channel, and delivery is not yet wired to approval/failure/completion events universally). |
| Aggregate "7 built / 24 partially built / 29 untouched" of 60 MUST | **Unreliable** | Withdrawn rather than restated — see the note above. Six of the inputs to that count were wrong, and re-deriving it honestly needs a per-FR re-verification the audit did not perform. |

**Why this drift happened, recorded so it can be prevented:** this section is a hand-maintained *summary* of per-FR state, updated only during periodic audits (2026-07-31, 2026-08-08, now 2026-08-11), while real work lands every step. It will lag again. That is precisely why the authority note above points at `feature_inventory.md` — which is updated in the same step as the code it describes — rather than at this block.

**Not built at all:** FR-033, FR-035–FR-037, FR-040, FR-042, FR-043, FR-045 (this three-item range is itself pre-existing drift not re-audited this step — FR-042/FR-043 already have real code per `feature_inventory.md` module 29's own row, `release`/`refactoring`), FR-044 (now real as of `P08-S01-M29-T07` — the Performance Agent, `ai_os_pack_software_engineering.agents.performance`, see `feature_inventory.md` module 29's own row), all of §7 except FR-098 (FR-090–FR-097, FR-099, FR-100 — the Dashboard/Voice/Notification interfaces those name are still not built; FR-098's own CLI is now real as of `P06-S04-M38-T01`, 5 of 8 documented command groups, see `feature_inventory.md` module 38's own row — this whole §7 line is otherwise pre-existing drift not re-audited this step, e.g. it does not yet reflect the Dashboard's own real Health/Workflows/Cost-and-Quality views), FR-114 (no replay mechanism — the run manifest itself is real, see FR-020 above), FR-115 (SHOULD — same real, partial slice as FR-019 above: the coverage query is real and correct, nothing autonomous calls it), and FR-078 (no historical per-model trend view across experiments — the one genuinely-unbuilt §6 requirement).

**Where to look for status (settled 2026-08-11 — see the authority note at the top of this section).** Per-module completeness: **`../../19_roadmap/feature_inventory.md`** (the authority; updated every step). Per-ticket completion: **`../../19_roadmap/STATUS.md` and `../../19_roadmap/MODULE_BOARD.md`** — both *generated* from the Task tickets under `../../19_roadmap/tickets/` (Phase R2, 2026-07-31) and guarded by a real staleness test. Scope and acceptance criteria: this document. Build history: `../../19_roadmap/history/INDEX.md`. **`implementation_status.md` is superseded** and should not be consulted — this line previously described `feature_inventory.md`'s completion table as "retired" alongside it, which was wrong and contradicted both `CLAUDE.md` and §9.1 of this same document.

---

## 2. Requirement Conventions

| Field | Meaning |
|---|---|
| ID | `FR-###`, permanent |
| Priority | `MUST` (v1), `SHOULD` (v1 if capacity allows), `LATER` (post-v1, recorded to prevent rediscovery) |
| Stage | Implementation stage from the Implementation Roadmap |
| Acceptance | The observable condition that proves it works |

---

## 3. Platform Kernel

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-001 | Load and validate a Capability Pack from a manifest, rejecting invalid packs without partial registration | MUST | B | An invalid manifest is rejected with a specific error and leaves no registration |
| FR-002 | Manage pack lifecycle through the canonical state machine (discovered → validated → installed → configured → activated → deactivated → uninstalled) | MUST | B | Every transition is recorded in `catalog.pack_state_transitions` |
| FR-003 | Activate and deactivate a pack without restarting the platform | MUST | B | A pack is deactivated and reactivated while workflows run; no dangling registrations |
| FR-004 | Execute a declared workflow graph, coordinating agents and tools | MUST | B | A sequential two-step workflow completes end to end |
| FR-005 | Persist workflow state durably as an append-only event log plus snapshot | MUST | B | Killing the worker mid-step loses no committed state |
| FR-006 | Resume a workflow after process restart or worker crash | MUST | B | A crashed worker's workflow resumes on another worker within the lease window |
| FR-007 | Route all model calls through the LLM Gateway with alias-based selection | MUST | B | No provider SDK import exists outside Gateway adapters (CI-enforced) |
| FR-008 | Support multiple providers simultaneously with retry, fallback, and circuit breaking | MUST | B | With provider A failing, the request completes on provider B and records `fallback_used` |
| FR-009 | Record tokens, cost, latency, cache split, and model identity for every model call | MUST | B | 100 % of calls attributable to workflow, agent, and pack |
| FR-010 | Assemble deterministic, budget-bounded, permission-aware context per step | MUST | B | Identical request + index generation → byte-identical context |
| FR-011 | Render versioned prompts with validated variables | MUST | B | A missing required variable fails before the model call |
| FR-012 | Execute quality gates and block progression on blocking failure | MUST | C | A failing blocking gate halts the workflow and records a structured result |
| FR-013 | Pause at a Human Approval Point and resume only on an authorized decision | MUST | C | Workflow enters `waiting_for_human`; resumes only after an authorized decision; timeout never approves |
| FR-014 | Publish platform events with correlation identifiers | MUST | B | Events carry `trace_id` and `workflow_id`; delivery is at-least-once |
| FR-015 | Report health and readiness for the Kernel and each active pack | MUST | A | Readiness returns 503 until critical components are functional |
| FR-016 | Resolve layered configuration with a single documented precedence order | MUST | A | Precedence is asserted by property tests |
| FR-017 | Resolve secrets by reference without exposing values in logs, state, or telemetry | MUST | A | A resolved secret never appears in any log, event, or audit payload |
| FR-018 | Enforce authorization by monotonic narrowing across principal, workflow, agent, tool | MUST | C | A tool cannot exercise a permission its agent or workflow lacks |
| FR-019 | Maintain traceability links and answer impact and coverage queries | MUST | D | "Which tests verify FR-012?" and "what is affected by changing module X?" both return correct results |
| FR-020 | Record a complete run manifest for every workflow run | MUST | D | Manifest passes schema validation and the run is re-launchable from it |
| FR-021 | Execute untrusted code only inside a Tier 1 sandbox | MUST | C | A Tier 1 step has no network, no secrets, and no host access; verified by test |
| FR-022 | Enforce per-step and per-workflow budgets | MUST | C | Exceeding a budget raises `BudgetExceededError` and halts the step |
| FR-117 | Verify a Capability Pack manifest's signature against a configured trust anchor before activation | MUST | A | A manifest whose signature is absent, malformed, or does not verify is refused activation when verification is required; the verification outcome is always recorded and reported, never assumed |

---

## 4. Product Creation (Software Engineering Pack)

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-030 | Accept a structured Markdown specification as workflow input | MUST | C | A specification is parsed into validated requirement items |
| FR-031 | Analyse requirements, detecting ambiguities and gaps, and produce structured requirements with acceptance criteria | MUST | C | Output validates against the Requirements Analyst output schema |
| FR-032 | Produce a solution architecture with component boundaries and recorded decisions | MUST | C | Architecture artifact produced and linked to requirements |
| FR-033 | Decompose approved architecture into an executable technical plan | MUST | C | Plan artifact conforms to the plan schema and drives a `foreach` step |
| FR-034 | Implement backend components from the plan | MUST | C | Generated code builds and passes generated tests in the sandbox |
| FR-035 | Implement frontend components from the plan | SHOULD | H | As FR-034 for frontend |
| FR-036 | Design database schemas and migrations | SHOULD | H | Migration applies cleanly and is reversible |
| FR-037 | Define versioned API contracts | SHOULD | H | Contract artifact produced and validated |
| FR-038 | Generate and improve automated tests to a coverage threshold | MUST | C | Coverage gate passes at the configured threshold |
| FR-039 | Review generated code and produce structured findings | MUST | C | Findings carry file, line, severity, and confidence |
| FR-040 | Perform security analysis of generated code | SHOULD | G | Security gate result recorded with findings |
| FR-041 | Produce and maintain documentation for generated software | MUST | C | Documentation artifact produced and linked in traceability |
| FR-042 | Manage version, changelog, and release readiness | SHOULD | H | Release gate evaluates and records readiness |
| FR-043 | Refactor existing code without changing observable behaviour | SHOULD | H | Tests pass before and after; behaviour assertions unchanged |
| FR-044 | Analyse performance characteristics and recommend optimisations | LATER | H | Report artifact produced |
| FR-045 | Iterate implementation through a bounded review–revise loop | MUST | C | Loop terminates on gate pass, iteration limit, or token ceiling |

---

## 5. Existing Project Intelligence

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-050 | Ingest an existing repository and build a structural model | MUST | E | Module and file inventory produced for a repository within NFR-006 limits |
| FR-051 | Detect languages, frameworks, and build systems in use | MUST | E | Detection report produced with confidence per finding |
| FR-052 | Construct module and dependency graphs | MUST | E | Graph artifact produced and queryable |
| FR-053 | Recover architectural boundaries and produce architecture documentation | MUST | E | Architecture recovery artifact produced |
| FR-054 | Identify entry points, APIs, and data stores | SHOULD | E | Inventory artifact produced |
| FR-055 | Assess technical debt and risk with scored findings | SHOULD | E | Scored, ranked findings produced |
| FR-056 | Generate documentation for a poorly documented system | MUST | E | Documentation set produced for a real repository |
| FR-057 | Produce prioritised modernisation recommendations with impact and effort estimates | SHOULD | E | Recommendation report produced |
| FR-058 | Write recovered knowledge back into the knowledge base with provenance | MUST | E | Recovered items retrievable, marked `untrusted`, with source provenance |
| FR-059 | Treat all ingested repository content as untrusted throughout the pipeline | MUST | E | Provenance tag `untrusted` present on every derived context item |

---

## 6. Multi-LLM Benchmarking

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-070 | Define an experiment pinning workflow version, prompts, tools, and configuration | MUST | D | Experiment definition validates and records pinned conditions |
| FR-071 | Execute the same workflow against multiple models with only the declared variable differing | MUST | D | Two models run the same definition; run manifests differ only in the model dimension |
| FR-072 | Execute repeated replicates per variant | MUST | D | Default ≥ 3 replicates recorded per variant |
| FR-073 | Collect quality, cost, performance, and process metrics per run | MUST | D | All four metric classes present per run |
| FR-074 | Produce a side-by-side comparison report with mean and variance | MUST | D | Report shows variance, not single-run point values |
| FR-075 | Exclude cache-served runs from comparison aggregates | MUST | D | A run with `served_from_cache = true` is excluded and flagged |
| FR-076 | Refuse to start an experiment whose projected cost exceeds its declared ceiling | MUST | D | Over-budget experiment is refused before any model call |
| FR-077 | Record any per-model prompt adaptation as a declared experiment variable | MUST | D | Adapted prompts appear in the report; unrecorded adaptation is impossible |
| FR-078 | Track model performance historically across experiments | SHOULD | H | Trend view available per model and metric |

---

## 7. Dashboard and Human Interfaces

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-090 | Show platform health, active workflows, pending approvals, recent failures, and cost | MUST | F | Overview renders live data |
| FR-091 | Show workflow list and detail with timeline, steps, gates, logs, and traces | MUST | F | Drill-down from list to trace works |
| FR-092 | Present pending approvals with decision context and accept a decision | MUST | F | An approval is decided from the Dashboard and the workflow resumes |
| FR-093 | Present experiment comparison views with drill-down to individual runs | MUST | F | Comparison view renders variance and links to runs |
| FR-094 | Show quality gate trends and most frequent failures | SHOULD | F | Trend view renders |
| FR-095 | Show token and cost breakdown by model, workflow, agent, and pack | MUST | F | Breakdown reconciles with `evaluation.llm_calls` |
| FR-096 | Stream live updates without full page reload | MUST | F | WebSocket updates observed in the workflow view |
| FR-097 | Show only actions the principal is authorized to perform | MUST | F | A `viewer` sees no mutating controls, and the API refuses them regardless |
| FR-098 | Provide a scriptable CLI for workflows, approvals, experiments, and health | SHOULD | H | CLI performs each operation with machine-readable output and meaningful exit codes |
| FR-099 | Provide a configurable voice interface for status, control, and approvals | SHOULD | F | Wake word, intent recognition, and a spoken status response work end to end |
| FR-100 | Preserve consistent state and authorization across all channels | MUST | F | An action started in one channel is visible and consistent in the others |

---

## 8. Governance, Knowledge, Observability

| ID | Requirement | Priority | Stage | Acceptance |
|---|---|---|---|---|
| FR-110 | Record every significant action in a tamper-evident audit log | MUST | C | Chain verification passes; tampering is detected |
| FR-111 | Require human approval for the defined governance decision set | MUST | C | Each listed decision type blocks without approval |
| FR-112 | Maintain the knowledge base with provenance and versioning | MUST | B | Retrieved items carry source and version |
| FR-113 | Provide correlated logs, metrics, and traces for every run | MUST | B | One `trace_id` links API request → workflow → agent → tool → model call |
| FR-114 | Support workflow replay from the event log | MUST | D | A completed workflow is reconstructed with no gaps |
| FR-115 | Report requirements lacking test coverage | SHOULD | D | Coverage query returns uncovered requirement IDs |
| FR-116 | Notify humans of approvals, failures, and completions across configured channels | MUST | F | Notification delivered and delivery status recorded |

---

## 9. Traceability

Every requirement above is linked in `trace.links` to the architecture elements that realise it, the modules that implement it, and the tests that verify it. The Traceability Engine answers:

- Which architecture elements realise `FR-###`?
- Which modules implement it?
- Which tests verify it?
- Which requirements currently have no verifying test? (FR-115)

A requirement with no verifying test is reported by the coverage query and is a release blocker for `MUST` items.

### 9.1 Traceability today

**Corrected 2026-08-11 (full-project audit): the `trace.links` table and the Traceability Engine are real.** This section previously said both were "not built"; direct inspection disproves it — the table is defined at `kernel/src/ai_os_kernel/persistence/trace_schema.py:109` and created by migration `0007_trace_artifacts_and_links.py`; `SqlTraceLinkWriter` is constructed in the real composition root (`kernel/src/ai_os_kernel/bootstrap.py`, `app.state.trace_link_writer`) and genuinely called from a production route (`kernel/src/ai_os_kernel/routes/delivery_pipeline.py`, which records a real `workflow_run --produced--> documentation` link); and two real HTTP readers exist, `GET /api/v1/traceability/impact/{external_id}` and `GET /api/v1/traceability/coverage` (`kernel/src/ai_os_kernel/routes/traceability.py`). What remains genuinely unbuilt is `GET /traceability/query` (the raw link graph) and any writer beyond the one delivery-pipeline link type — see `../../03_architecture/kernel/traceability_engine.md` and `feature_inventory.md` module 16.

Requirement-level coverage is still not automatic, though: no Agent or Workflow writes a `requirement --verified_by--> test` link, so the live view of which requirements have real code behind them remains **`../../19_roadmap/feature_inventory.md`** — its Section 5 completion table maps every documented module to a percentage derived from direct source inspection, and its Section 4 maps the Stage A–H phases to checkable exit criteria. **Use that document, not this one, to answer "is FR-### done?"** (see the authority note in the Implementation Status block above); use this document to answer "is FR-### in scope, and what proves it?"

Three known reconciliation gaps between this document's `Stage` column and `feature_inventory.md`'s phase assignments, recorded here rather than silently changed (either could be the one that is wrong; resolving it is a product-owner call):

- **FR-012** (quality gates) is `Stage C` here, but the Quality Gate Engine is tracked as a Phase **B** module in `feature_inventory.md` §5 row 15, because Stage B's own exit criteria in `../../19_roadmap/implementation_roadmap.md` call for two Kernel gates.
- **FR-098** (CLI) is `Stage H` here, but the CLI is tracked as a Phase **F** module (`feature_inventory.md` §5 row 38) and appears in Stage F's exit criteria.
- **FR-110** (tamper-evident audit log) is `Stage C` here, but audit is tracked inside the Phase **A** "Observability & Audit" module (`feature_inventory.md` §5 row 4).

---

## 10. Out of Scope for v1

Recorded so these are not rediscovered as gaps:

> **Scope change 2026-08-12 (product-owner decision).** "Signed manifests" has been removed from this list and is now in v1 scope as **FR-117** (§3). `security_architecture.md` §8 and `manifest_schema.md`'s own "Not in v1" section, both of which recorded it as a known accepted gap, are updated to match. The ticket that had been parked as permanently out of scope, `P01-S03-M28-T02`, is unblocked.

- Multi-tenancy and per-tenant isolation ([ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md))
- Domain packs beyond those listed (IoT, finance, analytics)
- A Capability Pack marketplace or third-party pack distribution
- Autonomous production deployment without human approval
- Non-English natural-language interfaces
- MCP as a platform interface ([ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md))

---

## 11. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Functional Requirements (this document)
4. Architecture Documents
5. Source Code

---

## 12. Related Documents

**Companion requirements documents**
- `../non_functional/nfr.md` — measurable targets for the same scope
- `../constraints/constraints.md` — the conditions this scope must work within

**Live build status (read these before assuming anything here exists)**
- `../../19_roadmap/feature_inventory.md` — per-module completion table; the authority on "% done"
- `../../19_roadmap/feature_inventory.md` — the authority on per-module completeness
- `../../19_roadmap/history/INDEX.md` — chronological build history
- `../../19_roadmap/implementation_roadmap.md` — Stage A–H sequence and exit criteria referenced by the `Stage` column

**Architecture documents realising these requirements**
- FR-001–FR-003 → `../../03_architecture/kernel/manifest_loader.md`, `../../03_architecture/kernel/capability_manager.md`, `../../03_architecture/capability_framework/capability_pack_contract.md`
- FR-004–FR-006, FR-013, FR-022 → `../../03_architecture/kernel/workflow_engine.md`, `../../03_architecture/workflow/workflow_architecture.md`, `../../03_architecture/workflow/state_management.md`, `../../03_architecture/workflow/workflow_patterns.md`, `../../03_architecture/workflow/error_handling_retry.md`
- FR-007–FR-009 → `../../03_architecture/kernel/llm_gateway.md`
- FR-010 → `../../03_architecture/kernel/context_manager.md`
- FR-011 → `../../03_architecture/kernel/prompt_engine.md`
- FR-012 → `../../03_architecture/kernel/quality_gate_engine.md`, `../../03_architecture/quality/quality_gates_framework.md`
- FR-014 → `../../03_architecture/kernel/event_bus.md`
- FR-015 → `../../03_architecture/kernel/health_lifecycle.md`
- FR-016 → `../../03_architecture/kernel/configuration_manager.md`, `../../03_architecture/services/configuration_management.md`
- FR-017 → `../../09_security/secrets_management.md`
- FR-018 → `../../03_architecture/kernel/security_manager.md`, `../../09_security/authentication_authorization.md`, `../../09_security/security_architecture.md`
- FR-019, FR-115 → `../../03_architecture/kernel/traceability_engine.md`, `../../03_architecture/traceability/traceability_model.md`
- FR-020, FR-070–FR-078 → `../../03_architecture/kernel/evaluation_engine.md`, `../../06_capability_packs/benchmarking/overview.md`
- FR-021 → `../../09_security/security_architecture.md` §5, `../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md`
- FR-030–FR-045 → `../../06_capability_packs/software_engineering/overview.md`, `../../06_capability_packs/software_engineering/agents.md`, `../../06_capability_packs/software_engineering/workflows.md`, `../../05_agents/agent_catalog.md`
- FR-050–FR-059 → `../../06_capability_packs/project_intelligence/overview.md`, `../../06_capability_packs/project_intelligence/agents_workflows.md`
- FR-090–FR-097 → `../../13_dashboard/dashboard_architecture.md`, `../../13_dashboard/information_architecture.md`, `../../13_dashboard/monitoring_experiment_views.md`
- FR-096 → `../../07_api/api_architecture.md`
- FR-098 → `../../07_api/cli_design.md`
- FR-099, FR-100 → `../../14_voice_jarvis/voice_architecture.md`, `../../14_voice_jarvis/multimodal_interaction.md`
- FR-110, FR-113 → `../../16_observability/observability_stack.md`, `../../03_architecture/kernel/observability.md`
- FR-111 → `../../03_architecture/governance/human_approval_points.md`
- FR-112 → `../../03_architecture/kernel/knowledge_manager.md`, `../../knowledge/knowledge_base_structure.md`
- FR-116 → `../../03_architecture/services/notification_service.md`

**Verification**
- `../../10_testing/test_strategy.md` — how these requirements are verified
- `../../20_glossary/glossary.md` — canonical definitions for the terms used above
