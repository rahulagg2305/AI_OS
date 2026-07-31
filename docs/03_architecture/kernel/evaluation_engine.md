# Evaluation Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Evaluation Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Evaluation Engine**, a core component of the AI_OS Platform Kernel.

The Evaluation Engine is responsible for measuring the quality, cost, performance, and other relevant metrics of workflows, agents, and especially multi-LLM experiments. It turns subjective impressions about “which model is better” into objective, comparable data.

This component is central to one of the primary goals of AI_OS: the ability to run the same project with different LLMs and rigorously compare the results.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Workflow Architecture  
6. Quality Gates Framework  

---

## Implementation Status (2026-07-31)

**Built:** Nothing behavioural still lives inside this package itself — `kernel/src/ai_os_kernel/evaluation_engine/` remains a docstring-only `__init__.py`, no Metrics Collector/Aggregator/Comparison Computer/Reporting Interface. **`evaluation.gate_results` now has a real, if narrow, writer (2026-07-31) — this engine's first real data producer, built deliberately in the Workflow Engine, not this package**, the identical "the functional gap is closed, not this package" shape `quality_gate_engine.md`'s own status section already established for `QualityGateStepExecutor`. `ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder`, injected into `WorkflowInstanceService` (optional, `None` by default — every existing caller unaffected) and composed by `se.delivery_pipeline`'s own trigger, writes one real row every time either of the two real `quality_gate` steps resolves, pass or fail — `gate_id`/`step_id` from the gate's own real step id, `gate_version` from the real workflow definition's own version (no Gate Registry exists to source a genuine gate-specific version from), `status` from the step's own real `workflow_steps.status`, `severity` fixed to the honest constant `"blocking"` (no warning-severity gate execution path exists in this codebase), `metrics` carrying the step's own real `attempt` number, `messages` carrying the real, already-recorded failure message on a failure or `[]` on a genuine pass, and `duration_ms` honestly `0` today (both real write paths that feed it stamp `started_at`/`completed_at` identically — a known, documented limitation of the current timestamp columns, not invented as a nonzero number). An unconfigured `quality_gate` step (no genuine evaluation ever ran) is correctly never recorded. Every other table this engine will eventually consume remains schema-only, real, migrated, and foreign-keyed in `kernel/src/ai_os_kernel/persistence/evaluation_schema.py` — `run_manifests`, `experiments`, `experiment_runs`, `metrics`, `llm_calls` (see `../../08_database/data_model.md` §6). The LLM Gateway also records per-call token/cost data (`kernel/src/ai_os_kernel/llm_gateway/call_recorder.py`) into `llm_calls`, and the Workflow Engine persists step and event records more broadly.

**Not built:** every component in §5 — no Metrics Collector, no Metrics Aggregator, no Run Manifest Recorder, no Comparison Computer, no Results Store writer, no Reporting Interface (the new `gate_results` writer above is a narrow, direct persistence write, not any of these designed components). Consequently **none of §6's mandatory experiment guarantees is enforced anywhere**: no run manifest is written (so no run is re-launchable under identical conditions, which is [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)'s central requirement), no per-replicate storage, no mean/variance computation, no `served_from_cache` exclusion, no prompt-adaptation recording. The Benchmarking Pack that §5.1 assigns experiment *definition* to does not exist either (`capability_packs/` contains only `software-engineering/` and a `_template/`), so neither side of that boundary is built. §3's metric categories have no collector beyond the one just named: the only other real metric in the entire Kernel is `aios.http.requests` (`kernel/src/ai_os_kernel/observability/metrics.py`). Roadmap stage: **D**.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (the schema itself: `005_catalog_and_evaluation_schema_buildout.md`).

---

## 2. Design Goals

The Evaluation Engine must:

- Provide objective, repeatable measurements
- Support comparison across different LLMs on the same project
- Capture both process metrics and outcome metrics
- Integrate with Quality Gates, Workflow Engine, and LLM Gateway
- Store results in a way that enables historical analysis and dashboards
- Remain domain-agnostic at the Kernel level (domain-specific metrics can be contributed by Capability Packs)

---

## 3. Types of Metrics

### 3.1 Cost Metrics
- Input tokens
- Output tokens
- Total tokens
- Estimated cost (per provider / model)
- Cost per workflow / per feature / per experiment

### 3.2 Performance Metrics
- Total workflow duration
- Duration per step / per agent
- LLM latency
- Tool execution time

### 3.3 Quality Metrics
- Quality Gate pass / fail results
- Test pass rate
- Code coverage
- Static analysis findings
- Security findings
- Architectural compliance score
- Documentation completeness

### 3.4 Process Metrics
- Number of retries
- Number of human interventions
- Number of failed gates
- Number of agent invocations
- Files changed / lines changed (when applicable)

### 3.5 Outcome Metrics (domain-contributed)
- Capability Packs may define additional metrics specific to their domain (e.g., maintainability score, business rule coverage, etc.)

---

## 4. Core Responsibilities

- Collect metrics from Workflow Engine, LLM Gateway, Quality Gate Engine, and other sources
- Aggregate metrics at workflow, experiment, agent, and project levels
- Support experiment definitions (same inputs, different LLMs)
- Produce comparison reports
- Store historical results
- Expose data to the Dashboard and to APIs

---

## 5. High-Level Structure

```text
Evaluation Engine
│
├── Metrics Collector
├── Metrics Aggregator
├── Run Manifest Recorder
├── Comparison Computer        (statistics: mean, variance, exclusions)
├── Results Store
└── Reporting Interface
```

### 5.1 Boundary with the Benchmarking Pack

v1.0 of this document and the Benchmarking Pack design both claimed to define, orchestrate, and report on experiments. The boundary is now explicit:

| Responsibility | Owner |
|---|---|
| Define an experiment (variables, pinned conditions, replicate count, cost ceiling) | **Benchmarking Pack** |
| Request runs | **Benchmarking Pack** — by submitting workflows to the Workflow Engine |
| Execute runs | **Workflow Engine** (the sole orchestrator) |
| Collect and store metrics | **Evaluation Engine** |
| Record the run manifest | **Evaluation Engine** |
| Compute comparison statistics (mean, variance, cache exclusions) | **Evaluation Engine** |
| Present and interpret the report | **Benchmarking Pack** and Dashboard |

The Benchmarking Pack does **not** orchestrate runs itself — that would breach the sole-orchestrator invariant ([ADR-0005](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md)). It defines and requests; the Workflow Engine executes; this engine measures.

The Evaluation Engine therefore has no "Experiment Manager" component: experiment *definition* lives in the pack, and per-run pinning is applied by the Configuration Manager and the LLM Gateway.

---

## 6. Experiment Support

An **Experiment** is a controlled run (or set of runs) of the same workflow / project with controlled variation (most commonly different LLMs).

The Evaluation Engine must support:

- Recording a complete **run manifest** per run, so the run is re-launchable under identical conditions
- Storing results per variant **and per replicate**
- Computing comparison statistics with **mean and variance across replicates** — never a single-run point value
- **Excluding any run with `served_from_cache = true`** from comparison aggregates, and flagging it in the report
- Recording any per-model prompt adaptation as a declared experiment variable, so an unrecorded adaptation cannot silently invalidate a comparison

Reporting a single run as a model comparison would be a methodological error: a non-deterministic system compared on one sample yields a number with no confidence attached. Replicates and variance are therefore mandatory, not optional ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)).

---

## 7. Key Design Rules

- Measurements must be as objective as possible.
- All metrics must be traceable back to a specific workflow run or experiment.
- Domain-specific metrics are contributed by Capability Packs; the Kernel provides the collection and storage infrastructure.
- Results must be durable and queryable.

---

## 8. Relationship with Other Components

- **Workflow Engine** emits execution events and outcomes.
- **LLM Gateway** emits token and cost data.
- **Quality Gate Engine** emits gate results.
- **Dashboard** consumes aggregated results and comparison reports.
- **Capability Packs** may register additional metrics.
- **Context Manager / Knowledge / Memory** may be evaluated indirectly through outcome quality.

---

## 9. Observability & Audit

Every metric and experiment result must carry:

- Workflow ID / Experiment ID / Trace ID
- Timestamp
- Source component
- Model / provider (when applicable)

---

## 10. Current Status

This document defines the design baseline for the Evaluation Engine. The four items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Storage design** | **Decided and already built.** PostgreSQL, SQLAlchemy Core, Alembic ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)). The concrete tables exist: `kernel/src/ai_os_kernel/persistence/evaluation_schema.py`, specified in `../../08_database/data_model.md` §6. Nothing further to design. |
| **Metric schemas** | **Decided at the storage level, open at the naming level.** `evaluation.metrics` and `evaluation.llm_calls` fix the row shape (see `data_model.md` §6), and the metric-naming convention `aios.<subsystem>.<metric>` is fixed by [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) / `../../16_observability/observability_stack.md`. **Named remaining gap:** the specific metric-name-to-column mapping for §3's four categories has not been enumerated — i.e. which of §3's measures are OpenTelemetry metrics (sampled, aggregated) versus `evaluation.metrics` rows (exact, per-run, never sampled). That distinction is load-bearing for §7's "traceable back to a specific workflow run": a sampled telemetry metric cannot satisfy it. Settling it is one enumeration pass over §3, not a new decision. |
| **Experiment definition format** | **Decided, and it is not this component's concern.** §5.1 assigns experiment definition to the **Benchmarking Pack** — as a declared pack artifact, since [ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) requires control flow to be declared rather than planned, and [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) makes packs the only extension point. The format therefore belongs in `../../06_capability_packs/benchmarking/overview.md`, not here. **Named remaining gap:** that pack does not exist, so the format is unwritten; this engine's side of the seam (`evaluation.experiments` / `evaluation.experiment_runs`) is already fixed and does not wait on it. |
| **Reporting APIs** | **Decided at the platform level, unbuilt.** REST under `/api/v1` with the conventions in `../../07_api/api_architecture.md` ([ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)); the consuming views are specified in `../../13_dashboard/monitoring_experiment_views.md`. Per §5.1, *presentation and interpretation* belong to the Benchmarking Pack and Dashboard — this engine exposes computed statistics, not reports. **Named remaining gap:** no route, no computation, no consumer exists yet. |

**One naming inconsistency worth noting, resolved in favour of this document:** §5.1 states this engine has **no "Experiment Manager" component**. Where other documents refer to an "Experiment Manager" applying pinned conditions, the real owners are the Benchmarking Pack (definition), the Configuration Manager's experiment-override layer (`configuration_manager.md` §4, layer 6), and the LLM Gateway (model pinning, `llm_gateway.md` §7). No such component is to be built.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Evaluation Engine Design  
6. Source Code

---

## 12. Related Documents

**Governing decisions (ADRs):**
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — run manifests, replicates, mean+variance, cache exclusion
- [ADR-0005 — Agents Never Communicate Directly](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — why the Benchmarking Pack cannot orchestrate its own runs
- [ADR-0011 — Persistence and Workflow State](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — the storage substrate
- [ADR-0017 — Observability Stack](../../18_decision_log/adr/ADR-0017-observability-stack.md) — telemetry vs. exact-measurement separation
- [ADR-0025 — Caching Strategy](../../18_decision_log/adr/ADR-0025-caching-strategy.md) — why cache-served runs are excluded
- [ADR-0006 — Quality Gates Are Mandatory](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) — gate results as a metric source

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `../workflow/workflow_architecture.md`
- `../quality/quality_gates_framework.md`

**Interacting subsystems:**
- `workflow_engine.md` — emits execution events and outcomes; the sole orchestrator of experiment runs
- `llm_gateway.md` — the sole producer of token and cost data (§9 there: one producer, so cost is reconcilable)
- `quality_gate_engine.md` — emits gate results
- `configuration_manager.md` — §4 layer 6, isolated experiment overrides
- `prompt_engine.md` — prompt-version pinning for fair comparison
- `observability.md` — the telemetry pipeline this engine sits beside, not inside
- `traceability_engine.md` — traceability coverage as a quality signal
- `../platform/platform_sdk.md` — pack-contributed metrics arrive across this boundary
- `../../06_capability_packs/benchmarking/overview.md` — owns experiment definition, submission, and reporting (§5.1)
- `../../13_dashboard/monitoring_experiment_views.md` — the comparison views

**Owned tables:**
- `../../08_database/data_model.md` §6 — `evaluation.run_manifests`, `.experiments`, `.experiment_runs`, `.metrics`, `.gate_results`, `.llm_calls`

**Reference:**
- `../../20_glossary/glossary.md`
- `../../02_requirements/non_functional/nfr.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
