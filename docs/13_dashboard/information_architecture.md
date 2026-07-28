# Dashboard Information Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Dashboard Information Architecture (Screens & Views)  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** The `dashboard/` directory has **no tracked content at all** — no frontend project is scaffolded, no `package.json`, no React application. It is absent from a fresh clone (git does not track empty directories). Stage F deliverable. None of the ten documented navigation sections exists.

A reader should also note the Dashboard is specified as a pure client of the HTTP API and its WebSocket stream: **only 9 of ~45 documented endpoints exist, and the `/api/v1/stream` WebSocket route does not exist at all** (see `../07_api/api_architecture.md`). Most views specified here have no data source yet.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the Information Architecture of the AI_OS Dashboard — the major screens, views, and navigation structure that users will interact with.

It builds on the Dashboard Architecture document and focuses on what information is shown where.

This document is subordinate to:

1. Dashboard Architecture  
2. Human Approval Points Framework  
3. Evaluation Engine Design  
4. Observability Design  

---

## 2. Design Goals

The Information Architecture must:

- Make the most important information easy to find
- Support day-to-day operations (monitoring + approvals)
- Support deep investigation (logs, traces, failures)
- Support multi-LLM experiment comparison
- Scale as new Capability Packs are added
- Remain simple enough for regular use

---

## 3. Top-Level Navigation

Recommended primary sections:

1. **Overview**
2. **Workflows**
3. **Approvals**
4. **Experiments**
5. **Quality**
6. **LLM Usage & Cost**
7. **Agents**
8. **System Health**
9. **Logs & Traces**
10. **Settings** (user / project preferences)

---

## 4. Major Screens & Views

### 4.1 Overview
- Platform health summary
- Active workflows count
- Pending human approvals
- Recent failures / alerts
- Cost snapshot (today / this week)
- Quick links to the most important actions

### 4.2 Workflows
- **List view**: filterable list of workflow instances (status, type, time, experiment, pack)
- **Detail view**:
  - Status and timeline
  - Steps and agent invocations
  - Quality gate results
  - Inputs / outputs summary
  - Linked experiment (if any)
  - Logs and traces for this workflow
  - Actions (cancel, retry, inspect)

### 4.3 Approvals
- List of pending Human Approval Points
- Detail view with context needed for the decision
- History of past approvals / rejections
- Ability to Approve / Reject / Request Changes

### 4.4 Experiments
- List of experiments
- Experiment detail:
  - Configuration (models, pinned prompts, etc.)
  - Runs and their status
  - Side-by-side comparison (quality, cost, duration, retries, human interventions)
  - Drill-down into individual runs (links to workflow detail)

### 4.5 Quality
- Quality gate pass/fail trends
- Gate results by workflow / experiment / pack
- Most frequent failing gates
- Links to affected workflows

### 4.6 LLM Usage & Cost
- Token usage and cost over time
- Breakdown by provider / model
- Breakdown by workflow / experiment / agent
- Budget / quota status (if configured)

### 4.7 Agents
- Invocation counts and success rates
- Latency and error rates per agent
- Most active agents
- Links to related workflows

### 4.8 System Health
- Kernel health and lifecycle state
- Capability Pack status (activated, healthy, failed)
- Dependency health (storage, search, etc.)
- Recent component-level alerts

### 4.9 Logs & Traces
- Searchable logs with correlation IDs
- Trace view for a given Trace ID / Workflow ID
- Ability to move from a workflow detail into its trace and logs

### 4.10 Settings
- User notification preferences
- Default views / filters
- Project-level settings (where applicable)

---

## 5. Cross-Cutting UI Requirements

- Consistent use of status indicators (Running, Waiting for Human, Failed, Completed, etc.)
- Easy copy of Workflow ID / Trace ID
- Clear timestamps and durations
- Responsive layout
- Permission-aware (only show actions the user is allowed to perform)

---

## 6. Relationship with Other Components

- All data comes from platform APIs (Workflow Engine, Evaluation Engine, Observability, Capability Manager, etc.).
- Human Approval actions go back through authenticated APIs to the Workflow Engine.
- Experiment comparison views rely on the Evaluation Engine and Benchmarking Pack.

---

## 7. Current Status

This document defines the baseline Information Architecture for the Dashboard.

Visual design, exact layouts, and interaction details will be refined during implementation and UX design.

---

## 8. Final Authority

Order of precedence:

1. Dashboard Architecture  
2. Dashboard Information Architecture  
3. Detailed UI specifications  
4. Source Code
