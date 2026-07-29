# Software Engineering Pack – Workflows – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Software Engineering Pack – Workflows
**Version:** 1.1
**Status:** Approved
**Last Updated:** 2026-07-28 (added a "Currently Implemented Subset" section documenting the real `se.delivery_pipeline` workflow, and a row for it in §12's own permissions table — no other content changed)

---

## 1. Purpose

This document specifies the workflows provided by the Software Engineering Capability Pack. Each is a declared, validated graph executed by the Workflow Engine ([ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)).

This document was referenced by the Documentation Index and by `tools_quality_gates.md` before it existed; it now exists and is authoritative for this pack's workflows.

This document is subordinate to:

1. Capability Pack Contract
2. Workflow Architecture
3. Standard Workflow Patterns
4. Software Engineering Pack – Overview
5. Software Engineering Pack – Agents

---

## 2. Common Rules

Every workflow in this pack:

- declares `inputs_schema` and `outputs_schema`;
- references agents by fully-qualified ID (`software-engineering/<slug>`);
- declares the permissions it requires — the ceiling for every agent and tool inside it ([ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md));
- runs all code execution in Tier 1 sandboxes ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md));
- declares bounded loops: maximum iterations **and** a token/cost ceiling;
- declares its Quality Gates and Human Approval Points explicitly;
- acquires an isolated workspace per instance;
- emits traceability links as it produces artifacts.

Step type vocabulary: `agent`, `tool`, `decision`, `parallel`, `foreach`, `sub_workflow`, `quality_gate`, `human_approval`, `compensate`.

---

## Currently Implemented Subset (2026-07-28)

§§3–9 below describe this pack's full, intended workflow design. As of this date, exactly **one** real, declared workflow exists — `se.delivery_pipeline` — built under a separate product-owner reprioritization toward "the shortest real path to a working multi-agent software-engineering pipeline" (see `docs/19_roadmap/implementation_status.md`'s own header). It is **not** an implementation of `se.implement_task` (§4) — that document was checked directly against the real, shipped shape below during this reconciliation, and the two diverge on purpose, structure, and even which agents participate. This section records the real shape here, rather than force-renaming it into a fork of `se.implement_task` or leaving it undocumented.

### `se.delivery_pipeline` — Reprioritization Proof-of-Concept Pipeline

**Purpose:** prove a real, declared, four-step Workflow Engine pipeline end to end — design, implement, verify, and record one file — using this pack's own four currently-real agents (see `agents.md`'s own "Currently Implemented Subset").
**Real today.** Declared in `capability_packs/software-engineering/workflows/delivery_pipeline.yaml`, manifest entry `workflows[].id: se.delivery_pipeline`.

**Inputs:** `requirement` (string). **Outputs:** `documentationPath` (string).

**Graph (genuinely simpler than any of §§3–9 — no tools, no decisions, no loops, no quality gates, no human approval points):**

```text
1  agent   software-engineering/architecture   → a design proposal (free text)
2  agent   software-engineering/build          → one real file, written through the sandbox
3  agent   software-engineering/qa-test        → a real pass/fail, from a real sandboxed exit code
4  agent   software-engineering/documentation  → one real Markdown record of steps 2–3
```

**How this differs from `se.implement_task` (§4), checked directly, not assumed:**
- `se.implement_task` is a **sub-workflow**, invoked via `foreach` from a larger workflow (`se.product_creation`/`se.feature_addition`), with `task`/`architecture_ref`/`workspace_id` as inputs — it has no `architecture` or `documentation` step of its own, and is never meant to run standalone.
- `se.implement_task`'s own graph includes `fs.apply_patch`/`test.run` tool steps, two `decision` steps forming iteration loops (`max_iterations: 3`), a `code-reviewer` agent step, and a blocking `quality_gate` — none of which `se.delivery_pipeline` has.
- `se.delivery_pipeline` includes its own `architecture` and `documentation` steps, which `se.implement_task` deliberately does not (those belong to the *outer* workflow in the full design).

Both are real, intentional, differently-shaped things — `se.delivery_pipeline` is not a smaller or renamed `se.implement_task`; it is the reprioritization's own minimal, standalone, end-to-end proof, and the closest real analogue in this document's own §§3–9 is actually a drastically reduced `se.product_creation` (§3's own "Stage C Scope," §13, already names a similar reduced slice — steps 1, 3, 7, 8, 9 — but using `requirements-analyst`/`backend-developer`/`code-reviewer`, not this pipeline's own four agents).

**Step-output hand-off:** each step's genuine, persisted output reaches the next step's genuine input through `ai_os_kernel.context_manager.resolvers.WorkflowStepOutputResolver` (a Context Manager resolver, not a new orchestration mechanism — see `context_manager.md` §4 and `workflow_architecture.md`'s own Context Management section, both updated alongside this document to record it).

**No Quality Gates, Human Approval Points, or declared Tools** — deliberately out of scope for this proof-of-concept slice; see `implementation_status.md` for the recommended next steps that would add them.

---

## 3. `se.product_creation` — Full Product Creation

**Purpose:** turn a structured specification into working, tested, documented software.
**Satisfies:** FR-030 … FR-034, FR-038, FR-039, FR-041, FR-045.
**Stage:** C (thin slice), H (full).

**Inputs:** `specification_ref` (ArtifactRef, Markdown), `project_id`, `target_stack` (optional), `quality_profile` (default `standard`).
**Outputs:** `repository_ref`, `documentation_ref`, `test_report_ref`, `architecture_ref`, `gate_summary`.

**Graph:**

```text
 1  agent          requirements-analyst        → structured_requirements
 2  quality_gate   se.requirements_complete    (blocking)
 3  human_approval approval:decide:requirements
 4  agent          architecture                → architecture_document, adr_candidates
 5  quality_gate   se.architecture_compliance  (blocking)
 6  human_approval approval:decide:architecture
 7  agent          technical-planner           → implementation_plan  (plan artifact)
 8  foreach        implementation_plan.tasks   → sub_workflow se.implement_task
                   max_fanout: 8
 9  quality_gate   se.build · se.unit_tests · se.coverage · se.lint ·
                   se.type_check · se.security_scan          (parallel, blocking)
10  agent          documentation               → documentation_set
11  quality_gate   se.documentation_complete   (blocking)
12  agent          release                     → release_candidate
13  human_approval approval:decide:release
14  tool           git.create_pull_request
```

Notes that matter:
- Steps 3 and 6 are the governance line: no implementation begins until requirements and architecture are human-approved (FR-111).
- Step 7 produces a **plan artifact**; step 8 consumes it. This is how dynamic decomposition happens without dynamic control flow.
- Step 9's gates run in parallel because they are independent; all must pass.
- Step 14 pushes to a **feature branch** and opens a pull request. Direct push to a protected branch is not available in the tool surface.

**Failure handling:** a blocking gate failure at step 9 routes back into `se.implement_task` for the affected tasks, bounded by `max_iterations: 3` and a workflow token ceiling. Exhaustion escalates to a human. Rejection at step 3, 6, or 13 follows the declared rejection path (return to the preceding agent step with the reviewer's comments in context, or terminate).

---

## 4. `se.implement_task` — Single Task Implementation (sub-workflow)

**Purpose:** implement one planned task to a passing state. Used by `foreach` in larger workflows.
**Satisfies:** FR-034, FR-038, FR-039, FR-045.
**Stage:** C.

**Inputs:** `task` (plan task item), `architecture_ref`, `workspace_id`.
**Outputs:** `changed_files`, `test_files`, `review_findings`, `usage`.

**Graph:**

```text
 1  agent          backend-developer  (or frontend-developer / database, by task.kind)
                                       → implementation
 2  tool           fs.apply_patch      (tier1)
 3  agent          qa-test             → tests
 4  tool           test.run            (tier1)
 5  decision       tests_passed?  →  no → back to 1   (max_iterations: 3)
 6  agent          code-reviewer       → review_findings
 7  decision       blocking_findings?  →  yes → back to 1   (max_iterations: 3)
 8  quality_gate   se.unit_tests · se.lint · se.type_check   (blocking)
```

This is the **Request–Review–Revise** pattern with both an iteration cap and a token ceiling. Step 5 and step 7 share one combined iteration budget, so a task cannot ping-pong indefinitely between fixing tests and addressing review.

---

## 5. `se.feature_addition` — Feature Addition to an Existing Codebase

**Purpose:** add a feature to an existing repository without regression.
**Satisfies:** FR-030 … FR-034, FR-038, FR-039.
**Stage:** H.

**Graph:**

```text
 1  tool           git.clone_or_fetch          (tier2, credentials in service)
 2  agent          existing-project-analyzer   → codebase_model
       (from the Project Intelligence pack, invoked via the Workflow Engine)
 3  agent          requirements-analyst        → feature_requirements
 4  agent          architecture                → integration_design
 5  quality_gate   se.architecture_compliance  (blocking)
 6  human_approval approval:decide:architecture   (only if the design changes boundaries)
 7  agent          technical-planner           → implementation_plan
 8  foreach        plan.tasks → sub_workflow se.implement_task   max_fanout: 4
 9  quality_gate   se.build · se.unit_tests · se.integration_tests ·
                   se.coverage_delta · se.security_scan          (blocking)
10  agent          documentation               → updated_docs
11  human_approval approval:decide:release
12  tool           git.create_pull_request
```

`se.coverage_delta` gates that coverage does not *decrease* — an absolute threshold is the wrong gate for an existing codebase that may start below it.

Step 6 is conditional: a feature that fits within existing boundaries does not need architecture approval, which keeps the governance cost proportionate.

---

## 6. `se.bug_fix` — Defect Correction

**Purpose:** reproduce, fix, and regression-test a defect.
**Satisfies:** FR-034, FR-038, FR-039.
**Stage:** H.

**Graph:**

```text
 1  tool           git.clone_or_fetch
 2  agent          qa-test                → reproduction_test        (must fail)
 3  tool           test.run               (tier1) — asserts the new test FAILS
 4  decision       reproduced?  →  no → escalate to human (cannot fix what we cannot reproduce)
 5  agent          backend-developer      → fix
 6  tool           fs.apply_patch · test.run
 7  decision       reproduction_test_passes AND no_regressions?  →  no → back to 5  (max 3)
 8  agent          code-reviewer          → review_findings
 9  quality_gate   se.build · se.unit_tests · se.regression · se.lint  (blocking)
10  human_approval approval:decide:release
11  tool           git.create_pull_request
```

Steps 2–4 encode a rule worth being explicit about: **the workflow refuses to "fix" a defect it could not first reproduce with a failing test.** Without it, a model will confidently produce a plausible change that fixes nothing.

---

## 7. `se.code_review` — Standalone Review

**Purpose:** review a change set and produce structured findings.
**Satisfies:** FR-039, FR-040.
**Stage:** C.

**Graph:**

```text
 1  tool           git.clone_or_fetch · git.diff
 2  parallel
       ├─ agent  code-reviewer  → correctness_and_standards_findings
       ├─ agent  security       → security_findings
       └─ agent  architecture   → architecture_compliance_findings
 3  agent          code-reviewer (synthesis role) → consolidated_report
 4  quality_gate   se.review_complete   (warning)
```

Findings carry file, line, severity, confidence, and rationale. Per the review-harness guidance in the Agents document, reviewer agents are prompted for **coverage** — report everything with confidence and severity — and filtering happens in step 3, not inside each reviewer. A reviewer instructed to self-filter for severity under-reports.

---

## 8. `se.refactoring` — Behaviour-Preserving Improvement

**Purpose:** improve structure without changing observable behaviour.
**Satisfies:** FR-043.
**Stage:** H.

**Graph:**

```text
 1  tool           git.clone_or_fetch
 2  quality_gate   se.baseline_tests_pass   (blocking — refuse to refactor an already-failing tree)
 3  tool           test.capture_baseline    → baseline_results
 4  agent          refactoring              → refactor_plan
 5  foreach        refactor_plan.steps → { apply_patch · test.run }   max_fanout: 1
 6  quality_gate   se.behaviour_unchanged   (blocking — compares against baseline_results)
 7  agent          code-reviewer            → review_findings
 8  human_approval approval:decide:release
 9  tool           git.create_pull_request
```

Step 2 and step 6 together are the point of this workflow: refactoring is only meaningful against a green baseline, and "behaviour preserved" must be asserted mechanically rather than claimed. `max_fanout: 1` keeps refactor steps sequential so a failure is attributable to one change.

---

## 9. `se.release` — Release Preparation

**Purpose:** produce a release candidate with correct versioning and changelog.
**Satisfies:** FR-042.
**Stage:** H.

**Graph:**

```text
 1  agent          release        → version_decision, changelog
 2  quality_gate   se.release_readiness   (blocking: version correct, changelog present,
                                            all gates green, no open blocking findings)
 3  human_approval approval:decide:release
 4  tool           git.tag · git.create_release_notes
```

Deployment is deliberately **not** in this workflow. Production deployment is a separate, human-approved workflow with its own approval class, so that preparing a release cannot become deploying one.

---

## 10. Quality Gates Referenced

Defined in `tools_quality_gates.md`; listed here so the workflow graphs are self-contained.

| Gate | Severity | Checks |
|---|---|---|
| `se.requirements_complete` | blocking | Requirements structured, acceptance criteria present, no unresolved ambiguity flags |
| `se.architecture_compliance` | blocking | Layering, dependency direction, naming, no forbidden patterns |
| `se.build` | blocking | Build succeeds; dependencies resolve |
| `se.unit_tests` | blocking | All unit tests pass |
| `se.integration_tests` | blocking | All integration tests pass |
| `se.regression` | blocking | Regression suite passes |
| `se.coverage` | blocking | Coverage ≥ configured threshold (default 80 %) |
| `se.coverage_delta` | blocking | Coverage does not decrease |
| `se.lint` | blocking | Linter clean |
| `se.type_check` | blocking | Type checker clean |
| `se.security_scan` | blocking | No high/critical findings; no secrets detected |
| `se.documentation_complete` | blocking | Required docs exist; public APIs documented |
| `se.behaviour_unchanged` | blocking | Test results match captured baseline |
| `se.baseline_tests_pass` | blocking | Existing tests pass before work begins |
| `se.release_readiness` | blocking | Version, changelog, gate status, open findings |
| `se.review_complete` | warning | Review produced findings with required fields |

---

## 11. Human Approval Points

| Approval class | Used in | Decision |
|---|---|---|
| `approval:decide:requirements` | product_creation | Requirements are correct and complete |
| `approval:decide:architecture` | product_creation, feature_addition | Architecture is approved |
| `approval:decide:release` | all workflows that push | Change may be pushed / released |

Every one of these persists the workflow in `waiting_for_human`, records the context digest shown to the approver, and never proceeds on timeout ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).

---

## 12. Declared Permissions

| Workflow | Permissions |
|---|---|
| `se.product_creation` | `filesystem:read`, `filesystem:write`, `git:read`, `git:write`, `llm:invoke`, `sandbox:execute` |
| `se.implement_task` | `filesystem:read`, `filesystem:write`, `llm:invoke`, `sandbox:execute` |
| `se.feature_addition` | as product_creation |
| `se.bug_fix` | as product_creation |
| `se.code_review` | `filesystem:read`, `git:read`, `llm:invoke`, `sandbox:execute` |
| `se.refactoring` | as product_creation |
| `se.release` | `filesystem:read`, `git:read`, `git:write`, `llm:invoke` |
| `se.delivery_pipeline` (real today — see "Currently Implemented Subset" above) | `llm:invoke`, `sandbox:execute` |

No workflow in this pack requests `secret:manage`, `pack:manage`, or `config:write`.

---

## 13. Stage C Scope

The Stage C thin slice implements `se.implement_task` and a reduced `se.product_creation` (steps 1, 3, 7, 8, 9 with build and unit-test gates only, plus one Human Approval Point), using three agents: `requirements-analyst`, `backend-developer`, `code-reviewer`. This is the minimum that exercises the full architecture end to end — agent invocation, context assembly, model call, tool execution in a sandbox, quality gate, human approval, and durable state.

---

## 14. Final Authority

Order of precedence:

1. Project Constitution
2. Capability Pack Contract
3. Workflow Architecture
4. Architecture Decision Records
5. Software Engineering Pack – Workflows (this document)
6. Source Code

---

## 15. Related Documents

- [`overview.md`](overview.md) · [`agents.md`](agents.md) — the pack overview and the 5 real agents `se.delivery_pipeline` draws 4 of its 4 steps from
- [`tools_quality_gates.md`](tools_quality_gates.md) — the gate definitions referenced in §10, none of which `se.delivery_pipeline` currently declares
- [`../../03_architecture/workflow/workflow_architecture.md`](../../03_architecture/workflow/workflow_architecture.md) · [`../../03_architecture/kernel/workflow_engine.md`](../../03_architecture/kernel/workflow_engine.md) — the platform engine executing `se.delivery_pipeline`, including which of the 9 step types it actually runs
- [`../../03_architecture/kernel/context_manager.md`](../../03_architecture/kernel/context_manager.md) — `WorkflowStepOutputResolver`, the real step-output hand-off mechanism cited in the Currently Implemented Subset section
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
