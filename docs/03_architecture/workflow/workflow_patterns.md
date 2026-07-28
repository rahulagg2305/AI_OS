# Standard Workflow Patterns – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Standard Workflow Patterns  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Partially built — 1 of the 8 patterns below is real.**

**Built:** the **Sequential Pattern** only — `se.delivery_pipeline` chains four agent steps, each step's persisted output reaching the next step's input through a real Context Manager resolver.

**Not built — and structurally blocked, not merely unimplemented:** Parallel, Request-Review-Revise Loop, Human-in-the-Loop Gate, Quality Gate Pipeline, Fan-out/Fan-in, Compensation/Saga, and Experiment. Each depends on a workflow **step type that currently completes as a no-op** — `parallel`, `decision`, `sub_workflow`, `quality_gate`, and `human_approval` are all routed to `NoOpStepExecutor`, so a definition declaring them validates and runs but does nothing at those steps. `joinPolicy` is validated at load time but never honoured at run time. The Experiment pattern additionally needs the Evaluation Engine and Benchmarking pack, both 0% built.

A reader must not infer from a pattern being documented here that a workflow can use it today. Outstanding Stage B/C/D work.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the standard workflow patterns that should be used across AI_OS.

Patterns provide reusable, proven ways of orchestrating agents so that Capability Packs do not invent ad-hoc coordination logic. Consistent patterns improve reliability, observability, and maintainability.

This document is subordinate to:

1. Project Constitution  
2. Workflow Architecture  
3. Agent Architecture & Agent Contract  
4. Agent Communication & Coordination Rules  

---

## 2. Design Goals

Standard patterns must:

- Cover the most common orchestration needs
- Remain simple and composable
- Support Quality Gates and Human Approval Points
- Work with the existing Workflow Engine
- Be domain-agnostic at the pattern level

---

## 3. Core Patterns

### 3.1 Sequential Pattern

**Description:** Steps (agents) execute one after another in a fixed order.

**Use when:** Each step depends on the complete output of the previous step.

**Example:** Requirements → Architecture → Technical Planning → Implementation

---

### 3.2 Parallel Pattern

**Description:** Multiple agents or branches execute concurrently and then join.

**Use when:** Work can be safely performed in parallel (e.g., backend + frontend after architecture is approved).

**Notes:** A `parallel` step **must** declare its join policy — `all` (any branch failure fails the step), `any` (first success wins; others cancelled), or `collect` (all branches complete; failures returned as partial results). A parallel step with no declared policy fails validation rather than defaulting silently. Each branch operates within the workflow's isolated workspace; concurrent writes to the same path are a validation error at definition time, not a runtime race.

---

### 3.3 Request – Review – Revise Loop

**Description:** One agent produces work, another agent (or the same agent with a different role) reviews it, and the original agent revises until quality criteria are met or a limit is reached.

**Use when:** High-quality output is required (code, architecture, documentation).

**Typical participants:** Development Agent + Code Review Agent, or Architecture Agent + Review step.

**Controls (all mandatory):** a declared maximum iteration count, **and** a declared token/cost ceiling, a Quality Gate after each cycle, and an escalation path when the bound is reached. An iteration cap alone is insufficient — a loop can be bounded in count and still be unbounded in cost.

---

### 3.4 Human-in-the-Loop Gate Pattern

**Description:** Workflow pauses at a defined point and waits for explicit human approval before continuing.

**Use when:** Governance rules require human approval (architecture, production deployment, major scope changes).

---

### 3.5 Quality Gate Pipeline Pattern

**Description:** A series of Quality Gates are executed in sequence (or parallel) after a major piece of work.

**Use when:** Multiple independent checks must pass (build, tests, security, lint, coverage, etc.).

---

### 3.6 Fan-out / Fan-in Pattern

**Description:** A single step triggers multiple parallel work items (fan-out); results are later collected and synthesized (fan-in).

**Use when:** The same type of work must be applied to many items (e.g., analysing multiple modules of a legacy system).

---

### 3.7 Compensation / Saga-style Pattern

**Description:** When a later step fails, previously completed steps can be compensated (rolled back or mitigated) in reverse order.

**Use when:** Side effects have occurred and consistency must be maintained.

---

### 3.8 Experiment Pattern

**Description:** The same workflow is executed multiple times with controlled variation (most commonly different LLMs) while keeping prompts, tools, and configuration as identical as possible.

**Use when:** Performing multi-LLM comparisons or A/B testing of prompts/strategies.

**Owner:** Primarily used by the Evaluation / Experiment Engine in coordination with the Workflow Engine.

---

## 4. Pattern Composition

Complex workflows are built by composing the above patterns rather than inventing new coordination styles.

Example of a typical product-creation workflow:

1. Sequential (Requirements → Architecture)
2. Human-in-the-Loop (Architecture approval)
3. Parallel (Backend + Frontend + Database)
4. Request–Review–Revise loops inside each parallel branch
5. Quality Gate Pipeline
6. Human-in-the-Loop (Release approval)

---

## 5. Rules

- New patterns should be introduced only when existing ones are insufficient.
- Any new pattern requires documentation and, when significant, an ADR.
- Patterns must still obey the fundamental rule: agents never communicate directly.

---

## 6. Current Status

This document defines the initial set of standard workflow patterns.

Concrete workflow definitions inside Capability Packs should reference these patterns.

---

## 7. Final Authority

Order of precedence:

1. Project Constitution  
2. Workflow Architecture  
3. Agent Communication & Coordination Rules  
4. Standard Workflow Patterns  
5. Capability Pack specific workflows  
6. Source Code
