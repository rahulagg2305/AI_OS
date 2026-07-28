# Agent Specifications – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Agent Specifications
**Version:** 1.1
**Status:** Approved
**Last Updated:** 2026-07-28 (added Implementation Status recording the spec-vs-code divergence; corrected §1's internally-contradictory "three Stage C agents" claim; added `build` to §7's table; added Related Documents. No specification content changed.)

---

## 1. Purpose

The Agent Catalog names the agents and their responsibilities. This document specifies them at contract level: identity, I/O schemas, tools, prompts, permissions, model alias, and gates — enough to implement and test them.

**Three agents are specified in full below** — `requirements-analyst` (§4), `backend-developer` (§5) and `code-reviewer` (§6) — chosen when this document was written as the ones expected to be built first. They are *not* the same three agents that §7's table assigns to Stage C (`technical-planner`, `qa-test`, `documentation`); an earlier version of this sentence claimed they were, which was an internal contradiction, corrected here. The remaining agents follow the same template and are specified to the same depth as their stage is reached; §7 defines the template so there is no ambiguity about what "specified" means.

This document is subordinate to the Agent Architecture & Agent Contract and the Agent Catalog.

---

## Implementation Status (2026-07-28)

**This document does not currently specify the agents that exist, and does not currently describe the agents it specifies.** That divergence is the single most important thing to know before using it, so it is recorded plainly.

**Built: 5 agents.** `requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation` — all in `../../capability_packs/software-engineering/`, all declared in `../../capability_packs/software-engineering/manifest.yaml`. Four of them (`architecture` → `build` → `qa-test` → `documentation`) are chained in the one real workflow, `../../capability_packs/software-engineering/workflows/delivery_pipeline.yaml`.

**Specified in full here: 3 agents** — `requirements-analyst`, `backend-developer`, `code-reviewer`.

**The overlap is exactly one agent.** Consequences, all of them real:

1. **`backend-developer` (§5) and `code-reviewer` (§6) are fully specified but entirely unbuilt.** No module, no manifest entry, no prompt, no test. Their sections are design specification only.
2. **Four of the five built agents have no contract-level specification in this document at all.** `architecture`, `qa-test` and `documentation` appear only as rows in §7's deferral table; `build` did not appear anywhere until this revision added it. This violates this document's own rule that "an agent is not implementable until items 4, 5, 10, and 12 are written" — those four were built without items 10 and 12 ever being written here. Their real, narrower contracts are documented instead in `../../capability_packs/software-engineering/manifest.yaml` and in `../06_capability_packs/software_engineering/agents.md`'s "Currently Implemented Subset" section, which is honest about each one's reduced scope.
3. **The one agent that is both specified and built — `requirements-analyst` — does not match its specification in §4.** The real implementation (`../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/requirements_analyst.py`) is a deliberate first slice, narrower on every axis:

| §4 specifies | Reality in code |
|---|---|
| Input `RequirementsAnalystInput` with `specification_ref: ArtifactRef`, `project_id`, `existing_requirements`, `domain_context` | `RequirementsAnalysisInput` with one field: `requirement: str`. Not validated at runtime — no per-step input-mapping mechanism exists yet |
| Output with structured `requirements[]`, `ambiguities[]`, `gaps[]`, `assumptions[]`, `coverage_note` | `RequirementsAnalysisOutput` with one field: `analysis: str` — the model's completion verbatim, unparsed |
| Model alias `reasoning` | `coding-strong` |
| Tools `fs.read` (tier2), `doc.parse` (tier2) | None. The pack declares no Tools in its manifest at all |
| Permissions `filesystem:read`, `llm:invoke` | `llm:invoke` only |
| Prompts `se.requirements.analyze@1`, `se.requirements.detect_ambiguity@1` | One prompt, `requirements.analyze@0.1.0` (`../../capability_packs/software-engineering/prompts/requirements_analysis.md`). Note also the id-namespace and version-scheme mismatch: this document uses `se.<area>.<action>@<major>`, the real pack uses `<area>.<action>@<semver>` |
| Gate `se.requirements_complete` | No gate. The Quality Gate Engine is 0% built and the pack declares no gates |
| Behavioural requirements 1–4, each "an acceptance criterion, not advice" | None is enforced. 1 and 3 need the gate that does not exist; 4 (stable requirement IDs across re-runs) is not merely unenforced but currently unachievable, since the output contains no requirement IDs |
| Tests: deliberate omission → `gap`; vague criterion rejected; IDs stable across runs | `../../capability_packs/software-engineering/tests/test_requirements_analyst.py` exists and passes, but tests the real free-text slice — none of the three specified cases is present |

**Not built:** the other 12 agents (`technical-planner`, `backend-developer`, `frontend-developer`, `database`, `api-designer`, `devops`, `security`, `code-reviewer`, `release`, `refactoring`, `performance`, `existing-project-analyzer`). Also not built and assumed throughout this document: the Tool Invoker and any manifest-declared Tool (no `fs.read`, `fs.list`, `code.search`, `fs.apply_patch`, `build.run`, `git.diff` or `doc.parse` tool exists anywhere), the Quality Gate Engine (so no gate named in any section below is real), and the `ai-os-sdk` package that would supply `ArtifactRef`, `ContextItem`, `StepBudget` and `StructuredError` — `platform_sdk/` contains exactly one real file, `../../platform_sdk/schemas/manifest.schema.json`.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` (per-module completion table — rows 29–31 for this pack, row 18 for the Tool Invoker, row 15 for the Quality Gate Engine, row 27 for the SDK) and `../19_roadmap/implementation_status.md`. Build history: `../19_roadmap/history/INDEX.md`.

---

## 2. Identity Convention

**Agent IDs are fully qualified, kebab-case, and globally unique:**

```text
<pack_id>/<agent_slug>
```

for example `software-engineering/backend-developer`.

This replaces the two competing schemes that previously existed (bare kebab slugs in the Agent Catalog, `SE-0nn` codes in the pack's Agents document). `SE-0nn` codes are **withdrawn**; they are not aliases and must not appear in manifests, prompts, telemetry, or traceability links.

Ownership is single: exactly one pack owns each agent. `existing-project-analyzer` belongs to `project-intelligence`, not to `software-engineering`.

---

## 3. Common Contract

Every agent:

| Property | Rule |
|---|---|
| Statelessness | No state retained between invocations. Everything persists via Workflow State. |
| I/O | Pydantic models; input validated on entry, output validated before return |
| Context | Received from the Context Manager. An agent never retrieves context on its own. |
| Prompts | Requested from the Prompt Registry by ID and version. Never inline. |
| Model | Selected by **alias**. Never a literal model ID. |
| Side effects | Only through Tools via the Tool Invoker. |
| Errors | Returns a `StructuredError`; does not implement its own retry policy |
| Budget | Honours the `StepBudget` in its request; raises on exhaustion |
| Untrusted content | Treats every `untrusted` context item as data, never instruction |
| Telemetry | Emits span, tokens, cost, duration, and outcome |

---

## 4. `software-engineering/requirements-analyst`

**Version:** 1.0.0 · **Model alias:** `reasoning` · **Satisfies:** FR-031
> **Status: partially built, and the real agent does not match this specification.** A deliberate narrower first slice exists in code (free-text `analysis` output, no tools, no gate). See the Implementation Status block above for the field-by-field divergence table.

**Purpose:** Convert a specification into structured, testable requirements; surface ambiguities and gaps rather than inventing answers.

**Input**

```text
RequirementsAnalystInput
    specification_ref: ArtifactRef        # Markdown specification
    project_id: str
    existing_requirements: list[Requirement] | None
    domain_context: str | None
```

**Output**

```text
RequirementsAnalystOutput
    requirements: list[Requirement]
        requirement_id: str               # FR-###, stable within the project
        statement: str
        rationale: str
        acceptance_criteria: list[str]    # >= 1, each independently verifiable
        priority: must | should | later
        source_reference: str             # where in the spec this came from
    ambiguities: list[Ambiguity]
        location: str
        description: str
        proposed_interpretations: list[str]
        blocking: bool
    gaps: list[Gap]
        area: str
        description: str
        recommended_question: str
    assumptions: list[Assumption]         # each requires human confirmation
    coverage_note: str
```

**Tools:** `fs.read` (tier2), `doc.parse` (tier2)
**Permissions:** `filesystem:read`, `llm:invoke`
**Prompts:** `se.requirements.analyze@1`, `se.requirements.detect_ambiguity@1`
**Gate:** `se.requirements_complete`

**Behavioural requirements — these are the acceptance criteria, not advice:**
1. Every requirement has at least one verifiable acceptance criterion. A criterion like "works well" is rejected by the gate.
2. **It must not invent requirements.** Anything not derivable from the specification appears in `gaps` or `assumptions`, never in `requirements`. This is the Constitution's "No Invention of Requirements" made testable.
3. A `blocking: true` ambiguity fails the gate and forces human clarification.
4. Requirement IDs are stable across re-runs for the same specification, so traceability survives iteration.

**Tests:** a specification with a deliberate omission must produce a `gap`, not a fabricated requirement; a vague criterion must be rejected by the gate; IDs must be stable across two runs.

---

## 5. `software-engineering/backend-developer`

**Version:** 1.0.0 · **Model alias:** `coding-strong` (effort `xhigh`) · **Satisfies:** FR-034

**Purpose:** Implement one planned task as production-quality code plus the changes needed to make it build.

**Input**

```text
BackendDeveloperInput
    task: PlanTask
        task_id: str
        description: str
        target_files: list[str]
        interfaces_to_implement: list[str]
        acceptance_criteria: list[str]
    architecture_ref: ArtifactRef
    coding_standards_ref: ArtifactRef
    workspace_id: str
    existing_code_context: list[ContextItem]
    prior_attempt: PriorAttempt | None       # failures/findings from the last iteration
```

**Output**

```text
BackendDeveloperOutput
    changes: list[FileChange]
        path: str
        change_type: create | modify | delete
        content: str | None                  # full content for create/modify
        rationale: str
    new_dependencies: list[Dependency]       # explicit; never installed implicitly
    interfaces_implemented: list[str]
    notes_for_reviewer: str
    unresolved_concerns: list[str]
```

**Tools:** `fs.read`, `fs.list`, `code.search` (tier2); `fs.apply_patch`, `build.run` (tier1)
**Permissions:** `filesystem:read`, `filesystem:write`, `llm:invoke`, `sandbox:execute`
**Prompts:** `se.backend.implement@1`, `se.backend.revise@1`
**Gates:** `se.build`, `se.lint`, `se.type_check`

**Behavioural requirements:**
1. Implements **only** the task described. Unrequested refactoring, speculative abstraction, or extra files are gate failures, not bonuses.
2. New dependencies are declared in `new_dependencies` and installed only by a declared, network-permitted step — never silently by the agent.
3. On a revision iteration, `prior_attempt` is used: the agent must address the specific failures, not regenerate from scratch.
4. Writes code that matches the surrounding code's conventions and comment density.
5. Never writes a credential, and never weakens a security control to make a test pass.

**Tests:** given a task plus a deliberately failing build from `prior_attempt`, the revision must address the reported error; a task requesting one function must not produce three files.

---

## 6. `software-engineering/code-reviewer`

**Version:** 1.0.0 · **Model alias:** `reasoning` · **Satisfies:** FR-039

**Purpose:** Find real defects and standards violations in a change set, and report them with enough structure to be filtered and acted on.

**Input**

```text
CodeReviewerInput
    diff_ref: ArtifactRef
    changed_files: list[FileSnapshot]
    requirements: list[Requirement]
    architecture_ref: ArtifactRef
    coding_standards_ref: ArtifactRef
    review_mode: coverage | synthesis
```

**Output**

```text
CodeReviewerOutput
    findings: list[Finding]
        finding_id: str
        file: str
        line: int | None
        category: correctness | security | performance | maintainability |
                  standards | test_coverage | architecture
        severity: critical | high | medium | low
        confidence: float                    # 0.0–1.0
        summary: str
        failure_scenario: str | None         # concrete inputs → wrong behaviour
        suggested_fix: str | None
    blocking_findings: list[str]             # finding_ids that must be resolved
    requirements_coverage: list[RequirementCoverage]
    summary: str
```

**Tools:** `fs.read`, `code.search`, `git.diff` (tier2)
**Permissions:** `filesystem:read`, `git:read`, `llm:invoke`
**Prompts:** `se.review.coverage@1`, `se.review.synthesis@1`
**Gate:** `se.review_complete` (warning)

**Behavioural requirements — the important one is counter-intuitive:**
1. In `coverage` mode the agent reports **every** finding, including low-confidence and low-severity ones, each with `confidence` and `severity`. It does **not** self-filter for importance. Instructing a reviewer to "only report significant issues" measurably reduces real-defect recall, because the model applies the filter faithfully and silently drops genuine bugs. Filtering happens in `synthesis` mode or in the workflow step, where it is visible and tunable.
2. `failure_scenario` is required for any `correctness` or `security` finding: a defect claim without a concrete path to wrong behaviour is speculation.
3. Findings reference real lines in the diff; hallucinated locations are rejected by output validation.
4. `blocking_findings` contains only `critical` and `high` findings with `confidence >= 0.7`.

**Tests:** a change set with a seeded off-by-one must be reported with a `failure_scenario`; a finding with an out-of-range line must fail validation; coverage mode on a clean diff must return an empty list rather than manufacturing findings.

---

## 7. Specification Template for Remaining Agents

Each remaining agent from the Agent Catalog is specified to this depth before implementation begins in its stage:

```text
1  Identity            <pack_id>/<slug>, version, owning pack
2  Purpose             one paragraph, and what it explicitly does NOT do
3  Model alias         plus effort, and why that alias
4  Input model         every field typed, with units and constraints
5  Output model        every field typed; required vs optional explicit
6  Tools               tool IDs and trust tiers
7  Permissions         the minimum set
8  Prompts             prompt IDs and versions
9  Quality Gates       which gates apply to its output
10 Behavioural reqs    numbered, each independently testable
11 Failure modes       what it returns when it cannot complete
12 Tests               the specific cases proving 10 and 11
```

An agent is not implementable until items 4, 5, 10, and 12 are written. Sections 10 and 12 are what make the specification a contract rather than a description.

| Agent | Owning pack | Stage |
|---|---|---|
| `software-engineering/architecture` | software-engineering | H |
| `software-engineering/technical-planner` | software-engineering | C (plan artifact schema required by `foreach`) |
| `software-engineering/frontend-developer` | software-engineering | H |
| `software-engineering/database` | software-engineering | H |
| `software-engineering/api-designer` | software-engineering | H |
| `software-engineering/devops` | software-engineering | H |
| `software-engineering/security` | software-engineering | G |
| `software-engineering/qa-test` | software-engineering | C |
| `software-engineering/documentation` | software-engineering | C |
| `software-engineering/release` | software-engineering | H |
| `software-engineering/refactoring` | software-engineering | H |
| `software-engineering/performance` | software-engineering | H |
| `project-intelligence/existing-project-analyzer` | **project-intelligence** | E |

---

## 8. Cross-Pack Participation

Agents owned by `software-engineering` may participate in workflows declared by `project-intelligence`, and vice versa. This is not pack-to-pack coupling: the **Workflow Engine** invokes each agent, the workflow declares which agents it uses, and neither pack imports the other. Agent references across packs are resolved by the registry at workflow validation time, and a workflow referencing an agent from an inactive pack fails validation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Agent Architecture & Agent Contract
4. Agent Catalog
5. Agent Specifications (this document)
6. Capability Pack agent implementations
7. Source Code
