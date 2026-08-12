# AI Governance Framework – AI_OS

**Version:** 1.1  
**Status:** Active  
**Last Updated:** 2026-07-28 (corrected one stale use of *deterministic* left over from the ADR-0022 amendment; recorded which enforcement mechanisms exist in code today; added Related Documents. No governance principle changed.)

---

## Purpose

The AI Governance Framework defines how AI models, agents, workflows, modules, automations, and developers operate within the AI_OS platform.

It establishes the operational governance rules that ensure AI-generated outputs remain consistent, secure, traceable, measurable, auditable, predictable, and aligned with the Project Constitution.

This framework operates under the authority of the Project Constitution.  
If any conflict exists between this document and the Project Constitution, the **Project Constitution shall take precedence**.

---

## Objectives

- Ensure consistent behavior across all AI models and agents
- Maintain engineering quality throughout the software lifecycle
- Prevent unauthorized architectural or functional changes
- Preserve engineering knowledge
- Enforce traceability
- Ensure observability and auditability
- Enable secure autonomous software engineering
- Keep the platform independent of any specific AI provider

---

## Core Governance Principles

### Documentation First
AI shall use approved repository documentation as the primary source of truth.  
Conversation history shall never be considered authoritative.

### Constitution Compliance
Every AI-generated artifact shall comply with the AI_OS Project Constitution.

### Human-in-the-Loop
AI may analyze, recommend, generate, and automate.  
AI shall not make irreversible or governance-critical decisions without explicit human approval.

### LLM Agnosticism
The governance framework applies equally regardless of the underlying AI provider.  
All LLM interactions shall pass through the platform’s LLM Gateway.

### Explainability
Where appropriate, AI shall explain why a recommendation was made, which documents influenced it, which assumptions were used, and which constraints were applied.

### Reproducible Engineering
*(Amended 2026-07-25 by [ADR-0022](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md). The former "Deterministic Engineering" principle required identical outputs from identical inputs, which LLM inference cannot provide; an unenforceable rule undermines every other rule in this framework.)*

AI_OS requires **reproducibility**, defined as three obligations:

1. **Configuration reproducibility.** Every run records the complete set of conditions that determined its behaviour — workflow, agent, prompt, tool, and pack versions; resolved model and parameters; context pack versions; retrieval index generation and embedding model version; resolved configuration; Kernel version. This *run manifest* makes any run re-launchable under identical conditions.
2. **Deterministic platform behaviour.** Everything the platform itself does — context assembly, retrieval ranking, chunking, prompt rendering, gate evaluation, cost computation — is deterministic given identical inputs. Non-determinism is confined to the model call.
3. **Recorded non-determinism.** Model outputs, token counts, latency, cache behaviour, tool-call sequences, and gate outcomes are recorded per run. Any cross-model comparison uses repeated runs and reports variance; a single run is never treated as evidence.

The word *deterministic* is used in AI_OS only about platform behaviour, never about model output.

### Least Authority
Every AI agent shall operate with only the permissions required to perform its assigned responsibilities.

### Separation of Responsibilities
Every AI agent shall have clearly defined responsibilities and shall not perform work outside its approved scope unless coordinated through an approved workflow.

---

## AI Sources of Truth

AI models shall consult information in the following order:

1. Project Constitution  
2. AI Governance Framework  
3. Approved Architecture Documents  
4. Approved Specifications  
5. Project Documentation  
6. AI Context Packs  
7. Decision Records  
8. Repository Source Code  

**Conversation history is never an authoritative source.**

---

## Agent Governance Rules

Every AI agent shall:

- Have a unique identifier
- Have a clearly defined responsibility
- Declare its inputs, outputs, allowed tools, dependencies, and required permissions
- Operate only within its approved scope

Additional rules:

- No agent may modify another agent without explicit human approval
- No agent may bypass governance controls or quality gates
- No agent may communicate directly with an LLM provider
- Every significant agent action shall be logged

---

## Workflow Governance

Every workflow shall define:

- Purpose
- Trigger
- Inputs
- Processing steps
- Decision points
- Outputs
- Success criteria
- Failure handling
- Human approval points

A workflow's *shape* should remain declared, validated, and reproducible wherever practical — see *Reproducible Engineering* above and [ADR-0021](../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) (workflows are declarative; there is no runtime task planner). Per [ADR-0022](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md), *deterministic* is used in AI_OS only about platform behaviour, never about model output; this line previously said "deterministic" and was missed when that amendment was applied.

---

## Decision Governance

Every significant architectural or governance decision shall be recorded as an Architecture Decision Record (ADR) containing:

- Context
- Problem Statement
- Decision
- Alternatives Considered
- Consequences
- Approval Status

Agents may recommend decisions but shall not finalize governance-critical decisions.

---

## Human Approval Points (Mandatory)

The following always require explicit human approval:

- Requirements approval
- Architecture approval
- Production deployment
- Repository restructuring
- Security policy changes
- Changes to the Project Constitution or this Governance Framework
- Major architectural changes
- Introduction of Capability Packs that affect platform behavior
- Breaking API contracts
- Production database schema changes

---

## Quality Governance

Every AI-generated artifact shall be:

- Correct, Complete, Consistent
- Maintainable, Traceable, Testable
- Secure, Modular, Documented, Reviewable

Additionally:

- No code shall bypass defined quality gates
- No deployment shall proceed with unresolved critical security findings
- No undocumented public API shall be accepted
- Defined testing thresholds shall be satisfied before progressing

---

## Knowledge & Traceability Governance

AI shall ground its work using approved Specifications, Architecture Documents, AI Context Packs, Knowledge Repository, and Decision Records.

AI shall never invent requirements or architecture.

Every significant AI-generated artifact shall maintain traceability (Requirement → Architecture → Implementation → Tests).

---

## Observability and Audit

Every significant system activity should be recorded, including:

- Prompt execution
- Tool invocation
- LLM requests
- Agent and workflow execution
- State transitions
- Architectural decisions
- Human approvals
- Quality gate results

Execution traces should be available for replay and audit wherever practical.

---

## Prompt Governance

Prompts shall be version controlled, documented, reusable, modular, and independently maintainable.  
Business logic should reside in configuration rather than prompts whenever practical.

---

## Capability Pack Governance

Every Capability Pack shall:

- Operate independently of the Platform Kernel
- Publish its interfaces and contracts
- Follow platform standards
- Maintain documentation and traceability
- Support semantic versioning
- Be independently installable and removable

Capability Packs shall not bypass governance controls.

---

## Security Governance

AI-generated outputs shall follow secure engineering practices.  
AI shall never intentionally expose secrets, bypass authentication, introduce known insecure patterns, or weaken security controls.

Security-sensitive changes require explicit human review.

---

## Error Handling

When uncertainty exists, AI shall:

- Stop where appropriate
- Report the uncertainty
- Identify missing information
- Request clarification
- Avoid inventing solutions

Silent assumptions are prohibited.

---

## Enforcement

Any governance violation shall:

1. Halt the affected workflow where appropriate
2. Record the violation in the audit log
3. Escalate the issue to a human reviewer
4. Prevent progression until the violation is resolved

### Enforcement Mechanisms

Governance in AI_OS is enforced by machinery, not by good intentions. Each rule in this framework has a named mechanism:

| Rule | Enforced by |
|---|---|
| No agent communicates with a provider directly | Import-boundary check in CI; pack contract suite |
| No agent communicates with another agent | No agent-invocation capability exists on `PackContext` |
| Agents operate only within declared scope | Manifest validation + monotonic permission narrowing at invocation |
| No agent bypasses a quality gate | Gate invocation is owned by the Workflow Engine; agents have no gate-control capability |
| No unapproved governance decision proceeds | Workflow persists in `waiting_for_human`; only an authorized principal can resume |
| Every significant action is logged | Append-only, hash-chained audit log with a daily verification job |
| No secret is exposed | `SecretValue` type redacts on stringification; secrets absent from sandboxes |
| Documentation stays current | Documentation quality gate; contract snapshot tests |
| Every significant decision is recorded | ADR process, with the Decision Log index as the check |

A governance rule without a mechanism is a defect in this framework, and adding one requires naming its mechanism.

#### Which mechanisms exist in code today (2026-07-28)

The table above names the mechanism each rule *will be* enforced by. Most are not yet built, and a governance framework that implies otherwise is exactly the "false assurance" it exists to prevent — so the current state is recorded here rather than left to be discovered:

| Mechanism | In code today |
|---|---|
| No agent communicates with a provider directly | **Partly real.** The LLM Gateway is genuinely the only provider egress path in the codebase, but this is currently a convention held by review, not a check: no import-boundary CI rule exists and there is no pack contract suite. |
| No agent communicates with another agent | **Real.** `PackContext` exposes no agent-invocation capability, and the four chained agents pass data only through durable workflow state. |
| Agents operate only within declared scope | **Not built.** Manifests are schema-validated, but monotonic permission narrowing is not computed or enforced at invocation (ADR-0023). |
| No agent bypasses a quality gate | **Vacuously true.** No Quality Gate Engine exists; nothing evaluates a gate anywhere (ADR-0006). |
| No unapproved governance decision proceeds | **Not built.** The `approvals` table exists with no writer or reader; a `human_approval` step completes as a NoOp instead of pausing (ADR-0007). |
| Every significant action is logged | **Partly real.** Workflow events are append-only and complete; the separate `audit_log` table exists with no writer, no hash chain, and no verification job (ADR-0017). |
| No secret is exposed | **Real for what exists.** `SecretValue` redacts on stringification and no secret is injected into a sandbox; only the `env` backend exists, and there is no per-access audit or prompt-scanning defence (ADR-0024). |
| Documentation stays current | **Manual.** Enforced by the standing rules in `../process/standing_rules.md` and periodic audits; there is no documentation quality gate and no contract snapshot test. |
| Every significant decision is recorded | **Real.** 25 ADRs Accepted, indexed at `../18_decision_log/README.md`, each carrying an appended implementation-status note. |

Per-module detail: [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md).

---

## Related Documents

**Above this framework**
- [`project_constitution.md`](project_constitution.md) — supreme governing document; this framework operates under its authority

**Decisions that amend or implement these rules**
- [`../18_decision_log/README.md`](../18_decision_log/README.md) — Decision Log index, 25 Accepted ADRs
- [`../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md`](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — amended the *Reproducible Engineering* principle above
- [`../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md`](../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — *Separation of Responsibilities*
- [`../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md`](../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) — *Quality Governance*
- [`../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md`](../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md) — *Human Approval Points*
- [`../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md`](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) and [`ADR-0023`](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md), [`ADR-0024`](../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — *Security Governance* and *Least Authority*

**Designs these rules govern**
- [`../03_architecture/governance/human_approval_points.md`](../03_architecture/governance/human_approval_points.md)
- [`../03_architecture/quality/quality_gates_framework.md`](../03_architecture/quality/quality_gates_framework.md)
- [`../03_architecture/capability_framework/capability_pack_contract.md`](../03_architecture/capability_framework/capability_pack_contract.md)
- [`../09_security/security_architecture.md`](../09_security/security_architecture.md)
- [`../16_observability/observability_stack.md`](../16_observability/observability_stack.md)

**What exists today**
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_roadmap.md`](../19_roadmap/implementation_roadmap.md)
- [`../DOCUMENTATION_INDEX.md`](../DOCUMENTATION_INDEX.md) — master index

---

## Final Authority

This AI Governance Framework defines the operational governance rules for every AI model, agent, workflow, Capability Pack, and generated artifact within AI_OS.

Where any conflict exists, the **Project Constitution** remains the supreme governing document.