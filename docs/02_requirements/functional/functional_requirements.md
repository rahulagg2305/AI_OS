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

---

## 10. Out of Scope for v1

Recorded so these are not rediscovered as gaps:

- Multi-tenancy and per-tenant isolation ([ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md))
- Domain packs beyond those listed (IoT, finance, analytics)
- A Capability Pack marketplace or third-party pack distribution
- Signed manifests
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
