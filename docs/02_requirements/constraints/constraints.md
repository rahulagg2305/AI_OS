# Constraints – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Constraints and Assumptions
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

Constraints are conditions AI_OS must work within and cannot negotiate away. Recording them explicitly prevents designs that assume them away and prevents rediscovering them mid-implementation.

IDs are `CON-###`.

---

## Implementation Status (2026-07-28)

Constraints are binding conditions, not features, so "built" here means *enforced by real code or CI* rather than merely written down.

**Enforced today:** CON-001 (no domain logic in the Kernel — holds; all domain logic lives in `capability_packs/software-engineering/`), CON-002/CON-013 (all model access goes through the LLM Gateway; aliases only outside Gateway config), CON-003 (agents never call each other — the one real workflow hands off strictly via `WorkflowStepOutputResolver`), CON-006 (control flow is declared in `workflows/delivery_pipeline.yaml`, never planned at runtime), CON-008 (`DockerSandbox` is the config-driven default via `AIOS_SANDBOX_BACKEND` and delivers all 5 ADR-0016 Tier 1 guarantees, verified live), CON-014 (every state change is an appended event), CON-020/CON-021/CON-023/CON-024/CON-027 (Python 3.12, Postgres 16 + `pgvector` schema, Redis 7 provisioned, one async process per role, Windows development is real and load-bearing).

**Not yet enforced — known, tracked gaps:**
- **CON-004/CON-005** are currently **violated by design, under a documented dated exception**: no `ai-os-sdk` package exists (`platform_sdk/` contains exactly one real file, `../../../platform_sdk/schemas/manifest.schema.json`), so the Software Engineering pack imports Kernel internals directly. See the exception note in `../../03_architecture/capability_framework/capability_pack_contract.md`.
- **CON-007** — monotonic narrowing is documented and modelled but not enforced end-to-end; the Capability Manager does not check agent/tool permission subsets.
- **CON-009** — secrets never reach the sandbox (structurally true), but there is no prompt-assembly secret-leak scan, and only the `env` backend exists.
- **CON-010** — the `governance.audit_log` table exists as schema only: no writer, no hash chain computed, no verification job.
- **CON-011** — no Quality Gate Engine exists, so there is nothing yet to skip; the constraint is unexercised rather than satisfied.
- **CON-012** — no Human Approval execution path exists; the `approvals` table has no writer.
- **CON-022** — a container runtime is required and used in development, but there is no `Dockerfile` in the repository and no Kubernetes node configuration to constrain yet.
- **CON-026** — no Dashboard TypeScript toolchain exists; the `dashboard/` directory is empty and CI's frontend stage is a deliberate no-op.
- **CON-030–CON-038** are properties of the world and remain true; the platform absorbs CON-030, CON-031, CON-035 and CON-036 today (reproducibility framing, no sampling params in the request contract, retry/circuit-breaker/fallback, aliases-as-configuration). CON-032's capability matrix exists; CON-033 (prefix-stable prompt caching), CON-034 (provider token-counting endpoints) and CON-038 (egress controls) have no implementation.
- **CON-025** is moot in practice: there is no SQLite development mode — Postgres-backed integration tests use `tests/integration/_postgres_fixture.py`, which skips cleanly when Docker is unavailable.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Architectural Constraints (self-imposed, binding)

| ID | Constraint | Source |
|---|---|---|
| CON-001 | The Platform Kernel contains no domain-specific logic | Constitution; [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) |
| CON-002 | No component other than the LLM Gateway may communicate with a model provider | [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) |
| CON-003 | Agents never communicate directly with each other | [ADR-0005](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) |
| CON-004 | Capability Packs interact with the platform only through the Platform SDK | [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) |
| CON-005 | A Capability Pack may not depend on the Kernel, on services, or on another pack | [ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) |
| CON-006 | Workflow control flow is declared, never planned at runtime | [ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) |
| CON-007 | Authority may only narrow along the invocation chain; no runtime elevation exists | [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) |
| CON-008 | Untrusted code executes only in a Tier 1 sandbox | [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) |
| CON-009 | Secrets never enter a sandbox, workflow state, telemetry, or a prompt | [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) |
| CON-010 | The audit log is append-only and hash-chained | [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) |
| CON-011 | No blocking quality gate may be skipped or self-certified at runtime | [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) |
| CON-012 | A timeout on a Human Approval Point never implies approval | [ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md) |
| CON-013 | Model identifiers appear only as aliases outside Gateway configuration | [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) |
| CON-014 | Every persistent workflow state change is an appended event | [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) |

---

## 3. Technical Constraints

| ID | Constraint | Implication |
|---|---|---|
| CON-020 | Python 3.12+ for all backend components | Libraries must support 3.12; no 3.11-only dependency |
| CON-021 | PostgreSQL 16 with the `pgvector` extension is required in production | Managed Postgres offerings must support `pgvector` |
| CON-022 | A container runtime (Docker or Podman) must be available to worker processes | Constrains Kubernetes node configuration; no Docker socket mounting |
| CON-023 | Redis 7 is required in production | Not a system of record; loss is tolerable |
| CON-024 | The Kernel is a single async process per role | Blocking calls must be offloaded to threads |
| CON-025 | SQLite development mode cannot support retrieval, leasing, or concurrency | Such work requires a Postgres container |
| CON-026 | The Dashboard is a separate TypeScript toolchain | Two CI lanes, two dependency-audit surfaces |
| CON-027 | Windows is a supported development platform | Paths must be `pathlib`-based; container execution requires WSL2 or Docker Desktop |

---

## 4. External Provider Constraints

These are properties of the world, not choices, and the platform must absorb them.

| ID | Constraint | Implication |
|---|---|---|
| CON-030 | Model inference is not deterministic | Reproducibility is defined as pinned conditions plus recorded variance ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)) |
| CON-031 | Current frontier models reject `temperature`, `top_p`, and `top_k` | The Gateway request contract must not require them; behaviour is steered by prompt and effort |
| CON-032 | Providers differ in tool-calling, structured output, streaming, and thinking support | Requires the capability matrix and explicit degradation rules |
| CON-033 | Provider prompt caching is prefix-matched | Prompt assembly must keep prefixes byte-stable; volatile content goes after the cache boundary |
| CON-034 | Token counts are provider- and model-specific | Only provider token-counting endpoints may be used; never a foreign tokenizer |
| CON-035 | Providers impose rate limits and can return transient overload | Retry with backoff, circuit breaking, and fallback chains are mandatory |
| CON-036 | Provider APIs and model lineups change frequently | Model aliases are configuration; adapters are versioned and isolated |
| CON-037 | Model output may be refused by provider safety systems | The Gateway must surface a refusal as a distinct outcome, not as a generic error |
| CON-038 | Sending data to a provider is an egress event | Context minimisation and a no-training agreement are required for production providers |

---

## 5. Operational Constraints

| ID | Constraint | Implication |
|---|---|---|
| CON-040 | Model usage costs real money per call | Budgets are mandatory; experiments declare cost ceilings |
| CON-041 | Human approval introduces unbounded wall-clock delay | Workflows must be durable across days, not just process lifetimes |
| CON-042 | Agent steps can run for many minutes | Health probes, drain periods, and timeouts must be sized accordingly; no request may block on a step |
| CON-043 | Ingested repositories may be large and hostile | Resource limits and untrusted handling are mandatory |
| CON-044 | Single-tenant deployment in v1 | The project boundary is organisational, not a security boundary |

---

## 6. Assumptions

If an assumption proves false, the referenced decision must be revisited.

| ID | Assumption | If false |
|---|---|---|
| CON-050 | Scale stays within the NFR bounds (≤ 50 concurrent workflows, ≤ 5 M chunks) | Revisit [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) and [ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md) |
| CON-051 | One organisation uses one deployment | Revisit [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) for multi-tenancy |
| CON-052 | Postgres remains sufficient for hybrid search at this corpus size | Adopt a dedicated vector store |
| CON-053 | Capability Packs can share one Python environment without irreconcilable dependencies | Revisit process isolation |
| CON-054 | Container isolation is sufficient for the deployment's threat model | Enable gVisor or micro-VMs |
| CON-055 | Declarative workflows can express the required task shapes | Revisit [ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) with an explicit plan for preserving replay |

---

## 7. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Architecture Decision Records
4. Constraints (this document)
5. Source Code

---

## 8. Related Documents

**Companion requirements documents**
- `../functional/functional_requirements.md` — the capabilities these constraints bound
- `../non_functional/nfr.md` — NFR-001–NFR-009 quantify the scale assumptions behind CON-050

**Live build status**
- `../../19_roadmap/feature_inventory.md` — per-module completion table (the authority on which constraints are actually enforced by code)
- `../../19_roadmap/implementation_status.md` — current stage and blockers
- `../../19_roadmap/history/INDEX.md` — build history

**Architecture documents that enforce these constraints**
- CON-001, CON-004, CON-005 → `../../03_architecture/platform/system_architecture.md`, `../../03_architecture/platform/platform_sdk.md`, `../../03_architecture/capability_framework/capability_pack_contract.md`
- CON-002, CON-013, CON-031–CON-038 → `../../03_architecture/kernel/llm_gateway.md`
- CON-003 → `../../03_architecture/agents/agent_communication.md`, `../../05_agents/agent_catalog.md`
- CON-006, CON-014, CON-041, CON-042 → `../../03_architecture/kernel/workflow_engine.md`, `../../03_architecture/workflow/state_management.md`
- CON-007 → `../../09_security/authentication_authorization.md`, `../../03_architecture/kernel/security_manager.md`
- CON-008, CON-043, CON-054 → `../../09_security/security_architecture.md` §5, `../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md`
- CON-009 → `../../09_security/secrets_management.md`
- CON-010 → `../../16_observability/observability_stack.md`
- CON-011 → `../../03_architecture/quality/quality_gates_framework.md`, `../../03_architecture/kernel/quality_gate_engine.md`
- CON-012 → `../../03_architecture/governance/human_approval_points.md`
- CON-020–CON-027 → `../../03_architecture/platform/technology_stack.md`, `../../11_deployment/deployment_architecture.md`
- CON-021, CON-052 → `../../03_architecture/services/search_vector_search.md`, `../../08_database/data_model.md`
- CON-026 → `../../13_dashboard/dashboard_architecture.md`
- CON-040 → `../../03_architecture/kernel/evaluation_engine.md`, `../../06_capability_packs/benchmarking/overview.md`
- CON-044, CON-051 → `../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md`
