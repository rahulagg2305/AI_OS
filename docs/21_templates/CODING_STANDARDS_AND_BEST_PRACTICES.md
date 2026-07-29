# Coding Standards & Best Practices – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Coding Standards & Best Practices  
**Version:** 1.0  
**Status:** Mandatory  
**Last Updated:** 2026-07-24

---

## Purpose

This document defines the mandatory coding standards, engineering principles, architectural rules, and implementation practices for every component developed within AI_OS.

Its purpose is to ensure that every implementation is:

- Modular
- Consistent
- Readable
- Maintainable
- Testable
- Secure
- Observable
- Configurable
- Production-ready

These standards apply equally to human developers, AI models, AI agents, Capability Packs, Platform Services, Platform Kernel, SDKs, internal tools, infrastructure code, and generated code.

**Violation of these standards is considered a defect.**

---

## Implementation Status (2026-07-28)

**Verified against `.github/workflows/ci.yml`: `ruff check`, `ruff format --check`, `mypy --strict`, `pip-audit --strict`, and `gitleaks/gitleaks-action` are all real, running CI steps** — most of the Forbidden Practices list's `[CI]` markings are accurate. Two are not, found during this audit:

- **`mypy --strict` runs only against `kernel/src`, `kernel/alembic`, and `tests`** (`ci.yml` line 65, matching `[tool.mypy]` in `pyproject.toml` exactly, per that step's own comment) — **`platform_sdk/` and any Capability Pack are not type-checked in CI at all today**, contradicting this document's own "Untyped function definitions in `kernel/`, `platform_sdk/`, `platform_services/` **[CI]**" scope, which implies `platform_sdk/` is covered. It is not, though the gap is currently low-stakes since `platform_sdk/` holds only a JSON Schema and no Python.
- **"A Capability Pack importing `ai_os_kernel`... **[CI]**" is not mechanically enforced by anything.** No forbidden-import check exists anywhere in the Kernel or CI pipeline (confirmed by grep across `ci.yml`) — and the one real pack, `capability_packs/software-engineering/`, imports `ai_os_kernel` extensively and directly (`llm_gateway.adapters.anthropic_adapter`, `persistence.engine`, `persistence.settings`, and more), under the dated, now-hard-gated exception recorded in `../03_architecture/capability_framework/capability_pack_contract.md`. This rule is real *policy* — the exception is explicit and bounded by the Platform SDK gate — but it is not currently *enforced* by CI the way its `[CI]` tag claims; a second pack repeating the same import today would not be caught mechanically, only by review discipline and the standing-rules gate.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` and `../19_roadmap/implementation_status.md`.

---

## Scope

This document governs:

- Platform Kernel
- Platform Services
- Capability Packs
- Platform SDK
- APIs
- Internal Tools
- Infrastructure
- Automation Scripts
- Configuration
- Test Code
- AI-generated Code

---

## General Engineering Principles

### Documentation First
Code follows approved documentation. Architecture, requirements, interfaces, and specifications must exist before implementation.

### Readability First
Code is written for humans first and computers second.

### Simplicity
Choose the simplest design that satisfies the requirements. Avoid unnecessary abstraction, optimization, or clever code.

### Maintainability
Future maintainability always takes precedence over short-term convenience.

### Modularity
Every module shall have a single responsibility and should be independently testable, deployable, and replaceable.

### Reusability
Reusable logic shall be extracted into shared components. Avoid duplication.

### Consistency
Use consistent naming, structure, patterns, formatting, and architectural practices throughout the repository.

### Composition over Inheritance
Prefer composition over inheritance whenever practical.

### SOLID Principles
All production code shall strictly follow the SOLID principles.

### Clean Architecture & Hexagonal Architecture
Business logic shall remain independent of UI, databases, frameworks, AI providers, and infrastructure.  
External systems shall communicate through ports and adapters.

---

## Platform Architecture Rules

- Domain-specific functionality belongs inside **Capability Packs**.
- The Platform Kernel shall remain domain-agnostic.
- Modules shall be highly cohesive and loosely coupled.
- Circular dependencies are strictly prohibited.
- Modules shall communicate only through public interfaces, published contracts, approved APIs, or the Event Bus.
- Modules shall never access another module’s internal implementation.

---

## Interface-Driven Design (Mandatory)

- Every **replaceable** dependency shall be consumed through a `typing.Protocol` declared in `platform_sdk/contracts/`.
- **Dependency injection is by explicit constructor injection**, wired in the single composition root at `kernel/bootstrap.py`. No DI container, no service locator, no module-level singletons ([ADR-0010](../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)).
- Concrete implementations shall not be referenced directly within business logic; the composition root selects them.
- **An interface is justified when a second implementation is real or clearly imminent** (provider adapters, stores, transports, secret backends). A Protocol with exactly one implementation and no prospect of a second is over-engineering and shall not be created merely to satisfy this section ([ADR-0004](../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)).
- FastAPI's `Depends` is used only for HTTP request-scoped values (current principal, request-scoped security context), never as the platform DI mechanism.

---

## Configuration Standards

No configurable behavior shall be hardcoded.

The following shall always come from configuration where applicable:

- Model names
- API endpoints / URLs
- Timeouts
- Thresholds
- Retry counts
- Feature flags
- Paths
- Logging levels

Sensitive configuration shall use secure secret management.

---

## Naming Standards

The platform language is **Python 3.12** ([ADR-0008](../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md)), so conventions are Python-idiomatic. The `I`-prefixed interface naming in v1.0 of this document was a .NET convention and is **withdrawn**.

| Element | Convention | Example |
|---|---|---|
| Modules and packages | `snake_case` | `llm_gateway`, `workflow_engine` |
| Classes | `PascalCase` | `WorkflowEngine`, `AnthropicAdapter` |
| **Interfaces (`Protocol`)** | `PascalCase`, **no `I` prefix**, named for the capability | `LLMGateway`, `SecretProvider`, `Cache` |
| Implementations | Named for what makes them specific | `VaultSecretProvider`, `RedisCache` |
| Functions and methods | `snake_case`, beginning with a verb | `assemble_context`, `resolve_secret` |
| Async functions | Same; no `_async` suffix | `async def complete(...)` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TOKEN_BUDGET` |
| Private | Single leading underscore | `_normalize_response` |
| Pydantic models | `PascalCase`, suffixed by role | `AgentRequest`, `LLMResponse` |
| Type aliases | `PascalCase` | `ArtifactId` |
| Files and folders | `snake_case` | `context_manager.py` |
| Pack IDs, agent slugs | `kebab-case` | `software-engineering`, `backend-developer` |
| Tool, workflow, gate IDs | dot-namespaced lower snake | `build.run`, `se.product_creation` |

**Frontend (TypeScript, Dashboard only):** `PascalCase` components, `camelCase` functions and variables, `kebab-case` files, no `I` prefix on interfaces.

---

## Function & Class Design

- Functions shall perform one responsibility and minimize side effects.
- Classes shall follow Single Responsibility, hide implementation details, and be independently testable.

---

## Error Handling

- Fail fast and fail clearly.
- Never swallow exceptions or use empty catch blocks.
- Preserve diagnostic information.
- Prefer domain-specific exceptions where appropriate.

---

## Logging & Observability

Logging shall be structured, consistent, and actionable.

Logs should include Trace ID, Workflow ID, Agent ID, and Correlation ID where applicable.

Supported levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.

Sensitive information shall never be logged.

---

## Security Standards

Never hardcode credentials, API keys, or secrets.  
Always validate inputs, apply least privilege, and maintain auditability.

---

## Testing Standards

- Business logic must always be unit testable.
- Critical workflows require integration tests.
- Test names shall clearly describe behavior.
- Do not write tests that only validate mocks.
- Tests shall remain deterministic.
- Quality Gates will enforce coverage thresholds.

---

## AI-Generated Code Standards

AI-generated code shall satisfy the **same standards** as human-written code.  
It must be reviewed, maintainable, documented, and must pass quality gates.

---

## Forbidden Practices

Strictly prohibited. Items marked **[CI]** are mechanically enforced.

- Hardcoded credentials, API keys, model IDs, business rules, or URLs **[CI]**
- Importing a provider SDK outside `kernel/llm_gateway/adapters/` **[CI]**
- A Capability Pack importing `ai_os_kernel`, `ai_os_services`, or another pack **[CI]**
- Untyped function definitions in `kernel/`, `platform_sdk/`, `platform_services/` **[CI]** (`mypy --strict`)
- Empty exception handlers, or `except Exception: pass` **[CI]** (ruff)
- `eval`, `exec`, `pickle` on untrusted input, `shell=True`, string-built SQL **[CI]** (ruff `S` rules)
- Blocking I/O on the asyncio event loop
- Executing generated or untrusted code outside a Tier 1 sandbox
- Passing a secret value into a sandbox, a prompt, workflow state, telemetry, or a log
- Dead code or commented-out production code **[CI]**
- Circular or hidden dependencies **[CI]**
- Agent-to-agent invocation, in any form
- Constructing or mutating a `SecurityContext`
- Direct dependency on concrete implementations in business logic
- Inventing requirements or architecture
- Bypassing quality gates or approved architecture
- TODO comments in production-critical paths without a tracked work item

---

## Code Review Checklist

Before approving code, verify:

- [ ] Interface-driven design followed
- [ ] Dependency Injection used appropriately
- [ ] No hardcoded configuration
- [ ] Code is modular and loosely coupled
- [ ] Capability Pack boundaries respected
- [ ] Proper error handling and logging
- [ ] Security practices followed
- [ ] Tests are meaningful
- [ ] Documentation updated
- [ ] Traceability maintained
- [ ] No constitutional or governance rules violated

---

## Final Rule

When multiple implementation approaches are possible, always choose the solution that is:

- More modular
- More configurable
- More observable
- More testable
- More maintainable
- More secure
- More aligned with the Project Constitution and AI Governance Framework

---

## Related Documents

- [`../process/coding_standards.md`](../process/coding_standards.md) — the load-bearing subset applied day-to-day; this document remains the full authority
- [`../03_architecture/capability_framework/capability_pack_contract.md`](../03_architecture/capability_framework/capability_pack_contract.md) — the dated, hard-gated exception to this document's "no `ai_os_kernel` import" rule
- [`../09_security/security_architecture.md`](../09_security/security_architecture.md) §15 — the security-specific subset of these standards (`ruff S`, `pip-audit`, `gitleaks`)
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_status.md`](../19_roadmap/implementation_status.md) — live build status