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

This document defines the design baseline for the Evaluation Engine.

Detailed metric schemas, storage design, experiment definition format, and reporting APIs will be refined during implementation.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Evaluation Engine Design  
6. Source Code
