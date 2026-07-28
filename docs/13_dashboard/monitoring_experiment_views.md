# Real-time Monitoring & Experiment Comparison Views – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Real-time Monitoring & Experiment Comparison Views  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the requirements and design guidance for two critical Dashboard capabilities:

1. **Real-time Monitoring** of running workflows and platform health
2. **Experiment Comparison Views** for multi-LLM (and related) experiments

These views directly support the operational and comparative goals of AI_OS.

This document is subordinate to:

1. Dashboard Architecture  
2. Dashboard Information Architecture  
3. Evaluation Engine Design  
4. Benchmarking Pack – High-level Design  
5. Observability Design  

---

## 2. Real-time Monitoring

### 2.1 Goals
- Give operators immediate visibility into what is happening right now
- Surface problems quickly (failures, stuck workflows, pending approvals)
- Support efficient drill-down into details

### 2.2 Key Elements
- Live list of active workflows with status
- Indicators for workflows waiting on Human Approval
- Recent errors and failed quality gates
- Current system health (Kernel + critical services + packs)
- Streaming or frequently refreshed updates for important status changes

### 2.3 Design Rules
- Prefer clarity over density
- Make it easy to jump from a monitored item to its full detail view (workflow, logs, trace)
- Real-time mechanisms must not overload the platform (careful use of websockets/SSE/polling)

---

## 3. Experiment Comparison Views

### 3.1 Goals
- Make multi-LLM comparisons easy to understand
- Show objective differences in quality, cost, speed, and process metrics
- Support drill-down from summary to individual runs and workflows

### 3.2 Key Elements

**Experiment Summary**
- Experiment name, description, and configuration
- Models / providers included
- Overall status of runs
- High-level winner / ranking (when meaningful)

**Side-by-side Comparison Table**
- Model / provider
- Success rate
- Final quality gate results
- Total tokens and cost
- Duration
- Number of retries
- Number of human interventions
- Other relevant metrics from the Evaluation Engine

**Run-level Detail**
- Ability to open any individual run
- Link to the underlying workflow instance
- Access to logs, traces, and artifacts for that run

**Visual Aids**
- Simple charts for cost, duration, and quality metrics across models
- Clear indication when results are incomplete or still running

### 3.3 Design Rules
- Fairness and transparency are essential — show the configuration that was pinned
- Do not hide failures; make them visible
- Support export of comparison results when practical
- Keep the view usable even when many models are compared

---

## 4. Relationship with Other Components

- **Evaluation Engine** is the source of truth for experiment metrics and comparisons.
- **Benchmarking Pack** defines and orchestrates experiments.
- **Workflow Engine** provides the underlying run status and history.
- **Observability Stack** provides logs and traces for drill-down.
- **Dashboard Information Architecture** places these views in the overall navigation.

---

## 5. Current Status

This document defines the requirements and design guidance for real-time monitoring and experiment comparison views.

Detailed UI mockups and interaction patterns will be refined during frontend implementation.

---

## 6. Final Authority

Order of precedence:

1. Dashboard Architecture  
2. Dashboard Information Architecture  
3. Real-time Monitoring & Experiment Comparison Views  
4. Source Code
