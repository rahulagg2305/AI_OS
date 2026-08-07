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

## Implementation Status (2026-08-06)

**Built:** **This package's own first real code (`P04-S01-M12-T04`, 2026-08-07): a narrow, real Metrics Collector.** `ai_os_kernel.evaluation_engine.metrics_collector.SqlMetricsCollector` reads a completed workflow's own already-real, already-persisted data — `workflow_instances.total_tokens`/`.total_cost_usd` (Cost), `.completed_at - .created_at` (Performance), a real `COUNT` over `evaluation.gate_results` where `status != 'completed'` (Quality), a real `COUNT` over `workflow_steps` where `attempt > 1` (Process) — and writes five real `evaluation.metrics` rows, one real slice of each of §3's four categories, no new instrumentation added anywhere. **A real, disclosed, structural blocker, not silently worked around: `evaluation.metrics.run_id` is a `NOT NULL` foreign key to `experiment_runs`, and no `experiment`/`experiment_run` has ever been created in production** (the Benchmarking Pack that owns experiment *definition* is 0% built, see "Not built" below) — unlike `gate_results`/`run_manifests` (both `workflow_id`-only), no ordinary `se.delivery_pipeline` run can get a real metrics row today. Design fork resolved with the product owner: build the real writer now, proven end to end (`tests/integration/evaluation_engine/test_metrics_collector.py`) against a real Postgres with a real, schema-valid, hand-seeded `experiments`/`experiment_runs` row — the identical "build real, wire later" precedent already established below for the Gate Registry/`gate_results`/`run_manifests`. Not composed into `WorkflowInstanceService`/`se.delivery_pipeline` — `WorkflowInstance` carries no real `run_id` of its own to supply, so there is no real caller yet, not an oversight. **`evaluation.llm_calls` now has real rows from both real call paths (`P04-S01-M12-T09`/`T10`, 2026-08-05/06)** — the writer (`SqlLLMCallRecorder`) was always real; the gap was upstream on each of the two real paths. For `PromptedCompletionService.complete_from_prompt` (the `PromptedAgent`/demo composition), `AgentStepExecutor` never forwarded `stepId`/`agentId`/`workflowId` into a step's `inputs`, so that call's own recording guard never fired — fixed by forwarding all three (`step_executor.py`); the demo composition's own `catalog.agents`/`catalog.prompts` ids were also never cataloged (both real foreign keys `llm_calls` enforces), fixed by seeding both idempotently at startup (`bootstrap._seed_prompted_agent_catalog_rows`). For `se.delivery_pipeline`'s own SDK-native agents (`SqlAgentRegistry`-resolved, `capability_packs/software-engineering`), which call `LLMGatewayAdapter.complete()` directly and never touch `PromptedCompletionService` at all, `LLMGatewayAdapter` now records too (`P04-S01-M12-T10`) — reusing `SqlLLMCallRecorder` unchanged, sourcing `agent_id` from `SqlAgentRegistry`'s own already-resolved id (threaded through `build_pack_context`, construction-time) and `prompt_id`/`prompt_version` from a real, additive `ai_os_sdk.models.common.TraceContext` extension (both new optional fields; every LLM-calling agent in the one real pack already builds a `TraceContext` and now also passes its own already-known prompt id/version into it). Real catalog rows for this pack's own agents/prompts already existed via the real pack installer (`manifest_catalog_installer.py`), so no analogous foreign-key-seeding gap applied here. Recording is wrapped in its own `try`/`except` inside `LLMGatewayAdapter`, so a downstream recording failure can never lose an already-succeeded completion's response — the identical risk `P04-S01-M12-T09`'s own catalog-seeding fix already established the pattern for. As with `gate_results` below, **`evaluation.run_manifests` now has a real writer (`P04-S01-M12-T05`, 2026-08-05)**, built the same way, in the Workflow Engine: `ai_os_kernel.workflow_engine.run_manifest_recorder.SqlRunManifestRecorder`, injected into `WorkflowInstanceService` (optional, `None` by default) and composed at all three real sites (`bootstrap.py`'s worker loop and workflow trigger, `delivery_pipeline.py`'s pipeline composition). It fires exactly once, when `advance()` itself observes genuine completion, joining the run's own `workflow_steps` (highest `attempt` per `step_name` wins) against `catalog.agents`/`catalog.tools`/`catalog.packs` for real version data and `evaluation.llm_calls` for resolved provider/model, then writes one `evaluation.run_manifests` row and stamps the FK back onto `workflow_instances.run_manifest_id` (a column that existed, unwritten, since the schema migration). Four gaps were originally disclosed rather than fabricated; **gap 2 (resolved provider/model honestly `None`) is now closed for the `PromptedAgent`/demo composition** by `P04-S01-M12-T09` — proven by a real, dedicated integration test (`tests/integration/workflow_engine/test_prompted_agent_call_recording.py`) showing the recorded manifest's step entry genuinely carries `resolved_provider`/`resolved_model_id`, not `None`. **`P04-S01-M12-T10` closes it for `se.delivery_pipeline` too, now proven (`P04-S01-M12-T11`, 2026-08-06)** — a real, dedicated integration test (`test_delivery_pipeline.py::test_the_real_sdk_native_pipeline_closes_the_run_manifest_recorders_own_gap`) drives the real, catalog-installed pack through the real `SqlAgentRegistry` to genuine completion (via the real `approve-git-push` resume) and confirms every LLM-calling step's manifest entry genuinely carries a real `resolved_provider`/`resolved_model_id` (and, since this pack is genuinely catalog-installed, real `agent_version`/`pack_version` too — both also honestly `None` in every `InMemoryAgentRegistry`-based test). **A real, structural gap surfaced building this proof, not merely missing coverage:** the shared `EchoLLMGateway` echoes its input verbatim, but this pack's real, shipped `build.write_file` prompt asks a model to *follow* a `FILE_PATH`/`FILE_CONTENT_BEGIN`/`FILE_CONTENT_END` format in natural-language instructions — echoing that prompt text back is not a completion that follows it, and `BuildAgentEntrypoint`'s own real parser correctly refused it (`LintInstructionError`, confirmed by a real failing first run, not assumed). Fixed with a small, local, deterministic fake gateway (`_BuildCompatibleEchoGateway`, ADR-0015's own "fake network, real everything else") returning a fixed, valid `FILE_PATH`/`FILE_CONTENT_BEGIN`/`FILE_CONTENT_END` block regardless of caller — every other real LLM-calling step accepts any non-empty string as its own free-text output, so only `build` actually parses this content's specific shape. The other three remain: (1) "all model parameters actually sent" ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)) has no real source anywhere in the codebase; (3) context-pack IDs/versions and retrieval index/embedding generation are absent because `SqlContextAuditLogger` is not wired into any real composition; (4) "the resolved configuration set" is available (`ConfigurationManager.load()`) but deliberately deferred to its own follow-up step rather than threading a third collaborator through all three composition sites in that ticket. `evaluation.gate_results` also has a real, if narrow, writer (2026-07-31) — this engine's first real data producer, built deliberately in the Workflow Engine, not this package, the identical "the functional gap is closed, not this package" shape `quality_gate_engine.md`'s own status section already established for `QualityGateStepExecutor`. `ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder`, injected into `WorkflowInstanceService` (optional, `None` by default — every existing caller unaffected) and composed by `se.delivery_pipeline`'s own trigger, writes one real row every time either of the two real `quality_gate` steps resolves, pass or fail — `gate_id`/`step_id` from the gate's own real step id, `gate_version` from the real workflow definition's own version (no Gate Registry exists to source a genuine gate-specific version from), `status` from the step's own real `workflow_steps.status`, `severity` fixed to the honest constant `"blocking"` (no warning-severity gate execution path exists in this codebase), `metrics` carrying the step's own real `attempt` number, `messages` carrying the real, already-recorded failure message on a failure or `[]` on a genuine pass, and `duration_ms` honestly `0` today (both real write paths that feed it stamp `started_at`/`completed_at` identically — a known, documented limitation of the current timestamp columns, not invented as a nonzero number). An unconfigured `quality_gate` step (no genuine evaluation ever ran) is correctly never recorded. Every other table this engine will eventually consume remains schema-only, real, migrated, and foreign-keyed in `kernel/src/ai_os_kernel/persistence/evaluation_schema.py` — `experiments`, `experiment_runs`, `metrics`, `llm_calls` (see `../../08_database/data_model.md` §6). The LLM Gateway also records per-call token/cost data (`kernel/src/ai_os_kernel/llm_gateway/call_recorder.py`) into `llm_calls`, and the Workflow Engine persists step and event records more broadly.

**§5's Comparison Computer and Reporting Interface are now both real** (`P04-S01-M12-T06`/`T07`, 2026-08-07; `T08`, same day). `ai_os_kernel.evaluation_engine.comparison_computer.SqlComparisonComputer.compute()` reads what the Metrics Collector already wrote (`evaluation.metrics` joined to `experiment_runs`) and reports real mean/variance per (variant, metric) over that variant's own real, completed, non-cache-served replicates (`statistics.mean`/`statistics.variance` on `Decimal`, never `float`) — variance is honestly `None`, not fabricated, for fewer than two contributing replicates. `served_from_cache` runs are excluded from the aggregate *and counted*: `VariantComparison.excluded_cache_served_count` reports exactly how many were excluded per variant (FR-075), including the edge case where every one of a variant's replicates was cache-served (the variant still appears, flagged, not silently omitted as if it never ran). `ai_os_kernel.evaluation_engine.reporting_interface.EvaluationReportingInterface.get_report()` composes the same `SqlComparisonComputer` (no parallel computation) and returns a `ComparisonReport` — a pure, synchronous, queryable wrapper over one already-computed `ExperimentComparison` (`get_variant`, `get_metric`, and `compare_by_metric`, the one genuinely new, cross-variant pivot-by-metric-name view §4's "Comparison Report" concept calls for). **Not built:** a Metrics Aggregator (§3's per-category rollup across an entire experiment, distinct from Comparison Computer's per-metric mean/variance) or a Results Store writer (the report above is computed live from already-persisted `metrics`/`experiment_runs` on every call, never persisted as its own row — cheap enough to recompute given today's real data volumes, and avoids a new, unapproved schema addition). Neither has a real production caller yet, for the same reason the Metrics Collector doesn't: no `experiments`/`experiment_runs` row is ever created by any real, running workflow today. Consequently **most of §6's mandatory experiment guarantees remain unenforced in production, though the computation itself is real and tested**: mean/variance and `served_from_cache` exclusion are both real (above), but there is still no real per-replicate storage from an actual experiment run, and no prompt-adaptation recording. The Benchmarking Pack that §5.1 assigns experiment *definition* to does not exist either (`capability_packs/` contains only `software-engineering/`, `benchmarking/` — schema/validation only, no manifest — and a `_template/`), so neither side of that boundary is built — this is also exactly why the real Metrics Collector, Comparison Computer, and Reporting Interface above have no real production caller. §3's metric categories have no *other* real, additional collector beyond the ones just named: the only other real metric in the entire Kernel is `aios.http.requests` (`kernel/src/ai_os_kernel/observability/metrics.py`). Roadmap stage: **D**.

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
| **Metric schemas** | **Decided at the storage level, partially enumerated at the naming level.** `evaluation.metrics` and `evaluation.llm_calls` fix the row shape (see `data_model.md` §6), and the metric-naming convention `aios.<subsystem>.<metric>` is fixed by [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) / `../../16_observability/observability_stack.md`. `P04-S01-M12-T04` enumerated one real name per category — `aios.workflow.total_tokens`/`.total_cost_usd` (Cost), `.duration_seconds` (Performance), `.gate_failures` (Quality), `.step_retries` (Process) — all `evaluation.metrics` rows (exact, per-run, never sampled), never OpenTelemetry. **Named remaining gap:** the rest of §3's measures (per-step duration, test pass rate, code coverage, files/lines changed, etc.) remain unenumerated, and which of them are OTel-sampled versus `evaluation.metrics`-exact is still an open, per-measure call — that distinction is load-bearing for §7's "traceable back to a specific workflow run": a sampled telemetry metric cannot satisfy it. |
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
