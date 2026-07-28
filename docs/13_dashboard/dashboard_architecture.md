# Dashboard Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Dashboard Architecture  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the high-level architecture of the **Dashboard** in AI_OS.

The Dashboard is the primary visual interface for humans. It provides visibility into workflows, agents, quality gates, experiments, costs, logs, and system health, and it is also a channel for Human Approval Points.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Observability Design  
4. Human Approval Points Framework  
5. Evaluation Engine Design  

---

## 2. Design Goals

The Dashboard must:

- Provide clear real-time and historical visibility
- Support Human Approval workflows
- Surface multi-LLM experiment comparisons
- Show cost, quality, and performance metrics
- Be responsive and usable for day-to-day operations
- Respect authentication and authorization
- Remain extensible as new Capability Packs are added

---

## 3. Primary User Needs

- See what is currently running
- Understand the status and history of workflows
- Approve or reject Human Approval Points
- Compare LLM experiment results
- Inspect quality gate outcomes
- Monitor cost and token usage
- Investigate failures using logs and traces
- View system and pack health

---

## 4. High-Level Architecture

```text
User Browser
      │
Dashboard SPA        React 19 · TypeScript strict · Vite
      │              TanStack Router + Query · Tailwind · shadcn/ui · Recharts
      │              API client GENERATED from OpenAPI 3.1 (drift fails CI)
      │
      ├── REST      GET/POST /api/v1/…          (TanStack Query cache)
      └── WebSocket /api/v1/stream              (events applied into that cache)
      │
FastAPI API Layer    authentication · authorization · rate limiting
      │              (transport only — no business logic)
      │
┌─────┴────────────────────────────────────────┐
│  Platform Kernel & Services                   │
│  Workflow Engine · Evaluation Engine           │
│  Observability · Human Approval Points         │
│  Capability Manager · Notification Service     │
└──────────────────────────────────────────────┘
```

Stack decided in [ADR-0018](../18_decision_log/adr/ADR-0018-dashboard-technology-stack.md); API contract in `../07_api/api_architecture.md`.

**One transport, one cache.** REST reads populate the TanStack Query cache; WebSocket events are applied into the same cache. There is no second state store and no polling loop competing with the stream, which is what keeps a live multi-panel view consistent.

**Architectural rule:** the Dashboard contains presentation and interaction logic only. No orchestration, no evaluation computation, no business rules. Anything it needs computed is computed by the platform and exposed through the API — otherwise the same logic would exist twice, in two languages, and diverge.

---

## 5. Major Views (Information Architecture Preview)

- **Platform Overview** — health, active workflows, recent alerts
- **Workflows** — list, detail, timeline, logs, state
- **Human Approvals** — pending decisions and history
- **Experiments & Comparisons** — multi-LLM results
- **Quality Gates** — pass/fail trends and details
- **LLM Usage & Cost** — tokens, cost, provider breakdown
- **Agents** — invocation stats and performance
- **System / Pack Health** — Kernel and Capability Pack status
- **Logs & Traces** — investigative views

Detailed information architecture is covered in a subsequent document.

---

## 6. Key Design Rules

- The Dashboard is a client of the platform; it does not embed business logic that belongs in the Kernel or Capability Packs.
- All data access must go through authenticated and authorized APIs.
- Real-time updates (where needed) should use efficient mechanisms (websockets, SSE, or polling with care).
- The Dashboard must support the Human Approval Point flow cleanly.
- Multi-LLM comparison views are a first-class requirement.

---

## 7. Relationship with Other Components

- **Workflow Engine** provides status and history.
- **Evaluation Engine** provides experiment and metric data.
- **Observability Stack** provides logs, metrics, and traces.
- **Human Approval Points** are surfaced and acted upon here.
- **Notification Service** feeds in-app notifications.
- **Capability Manager** provides pack health and status.
- **Security Manager** enforces authentication and authorization.

---

## 8. Current Status

This document defines the high-level Dashboard Architecture.

Subsequent documents will detail the Information Architecture (screens and views), real-time monitoring, and experiment comparison views.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Dashboard Architecture  
4. Detailed Dashboard documents  
5. Source Code
