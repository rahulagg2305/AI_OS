# Benchmarking Pack – High-level Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Benchmarking Pack – High-level Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-07)

**Built: four real, narrow modules — `capability_packs/benchmarking/` is now a real, buildable distribution (`P04-S03-M34-T01` through `T04`), no longer absent from a fresh clone.** `experiment_definition.py` validates a raw spec against §7's own rules (≥3 replicates, ≥2 variants, no duplicate keys, no sampling-parameter variables, an optional positive `cost_ceiling_usd`, a genuinely-existing pinned workflow). `replicate_management.py` expands a validated variant into its own numbered replicates. `cost_ceiling.py` refuses a projected-over-ceiling experiment before any call (enforcement only — computing a real, non-approximated projection remains real, disclosed, unbuilt work). `prompt_adaptation.py` records a genuine per-model prompt adaptation as a declared `variables` entry, closing §7's own "anything varying that was not declared... invalidates the experiment" rule for this one real case. Two real Kernel-side adapters (`ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter`/`experiment_run_recorder_adapter`) implement this pack's own declared Protocols, since this pack's source may never import `ai_os_kernel`. **No experiment can yet be submitted, executed, or reported** — nothing above is wired into a real submission path (no `manifest.yaml` exists either; nothing here needs pack activation yet), matching this whole slice's own consistent "build real, wire later" precedent.

The Evaluation Engine that this pack depends on for all metric collection, run-manifest recording, and comparison statistics has its own first real code too (`ai_os_kernel.evaluation_engine.metrics_collector`, `P04-S01-M12-T04`) — though it likewise has no real production caller yet, for the identical reason (no real `experiment_runs` row exists in production). One Stage D prerequisite *has* landed early: a second real provider adapter (`LocalAdapter`), so multi-provider comparison is mechanically possible once submission/execution exist. Stage D deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document provides the high-level design of the **Benchmarking Capability Pack**.

The Benchmarking Pack enables AI_OS to run controlled, repeatable experiments that compare different LLMs (and optionally different prompts, configurations, or strategies) on the same software engineering tasks. It turns the original product vision of “compare LLMs on real work” into a concrete platform capability.

This document is subordinate to:

1. Project Constitution  
2. Capability Pack Contract  
3. System Architecture  
4. Evaluation Engine Design  
5. Workflow Architecture  

---

## 2. Goals of the Pack

The Benchmarking Pack shall enable:

- Definition of experiments (same task, controlled variation)
- Execution of the same workflow against multiple LLMs
- Collection of objective metrics (quality, cost, speed, retries, human interventions, etc.)
- Side-by-side comparison reports
- Historical tracking of model performance
- Fair comparison by pinning prompts, tools, and configuration

---

## 3. Scope

### In Scope
- Experiment definition and management
- Multi-LLM execution orchestration
- Metric collection coordination with the Evaluation Engine
- Comparison report generation
- Integration with Dashboard for visualisation
- Support for prompt / configuration pinning

### Out of Scope
- Actual software engineering logic (belongs to Software Engineering Pack)
- Low-level metric storage (belongs to Evaluation Engine)
- Voice interface

---

## 4. Key Concepts

### Experiment
A controlled set of runs of the same workflow (or project) with deliberate variation — most commonly different LLMs — while keeping other factors as constant as possible.

### Run
A single execution of a workflow within an experiment, associated with a specific model / configuration.

### Comparison Report
A structured summary that shows how different models performed on the same work across quality, cost, performance, and process metrics.

---

## 5. High-Level Flow

1. User (or system) defines an Experiment
2. Experiment pins workflow version, prompts, tools, and configuration
3. Experiment specifies the models to compare **and the replicate count** (default ≥ 3)
4. The pack **submits** runs to the Workflow Engine — it does not orchestrate them itself
5. Each run uses the LLM Gateway with the pinned model; fallback is disabled unless declared
6. Evaluation Engine records the run manifest, collects metrics, and computes comparison statistics
7. Benchmarking Pack presents and interprets the report
8. Results are available on the Dashboard and via API

**Boundary note.** Step 4 is a submission, not an orchestration: the Workflow Engine remains the sole orchestrator ([ADR-0005](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md)), and the statistical computation in step 6 belongs to the Evaluation Engine, not this pack. See `../../03_architecture/kernel/evaluation_engine.md` §5.1 for the full split.

---

## 6. Relationship with Other Components

- **Evaluation Engine** is the primary consumer and store of metrics.
- **Workflow Engine** executes the actual work for each run.
- **LLM Gateway** routes calls to the model selected for each run.
- **Prompt Engine** supports pinning of prompt versions.
- **Configuration Manager** supports experiment-level overrides.
- **Dashboard** visualises comparison results.
- **Software Engineering Pack** provides the workflows being benchmarked.

---

## 7. Key Design Rules

- Experiments must be reproducible in the sense defined by [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md): pinned conditions, deterministic platform behaviour, recorded non-determinism.
- Variation must be deliberate and recorded. Anything varying that was not declared as a variable invalidates the experiment.
- Fairness requires pinning every variable except the declared one. Prompts are held **byte-identical across models** by default; a required per-model adaptation is recorded as a declared variable and reported.
- **Sampling parameters are not experiment variables.** Current models reject `temperature`/`top_p`/`top_k`, so they are absent from the Gateway contract and cannot be varied.
- **Response caching is disabled for experiment runs**, enforced in the Gateway. A cache-served run is excluded from aggregates and flagged ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)).
- A comparison reports **mean and variance over replicates**, never a single run.
- All runs must be fully observable and linked to the parent experiment and its run manifest.

---

## 8. Current Status

This document defines the high-level design of the Benchmarking Pack.

Detailed experiment schema, report formats, and integration contracts will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. Capability Pack Contract  
3. Evaluation Engine Design  
4. Benchmarking Pack – High-level Design  
5. Source Code
