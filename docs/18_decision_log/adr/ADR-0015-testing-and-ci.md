# ADR-0015: Testing Strategy and CI Toolchain

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/10_testing/test_strategy.md`, `docs/03_architecture/quality/quality_gates_framework.md`

---

## Context

Five classes of test are mandated for every Capability Pack and coverage thresholds are mandated by the Quality Gates Framework, but no framework, runner, or CI system had been chosen — so none of it could run. AI_OS also needs its *own* quality gates to run on itself, using the same tooling it will later run on generated code.

## Decision

| Concern | Tool | Rationale |
|---|---|---|
| Test runner | `pytest` + `pytest-asyncio` (strict mode) | Standard, async-capable, best fixture model. |
| Coverage | `pytest-cov` (branch coverage) | Thresholds: **90 % kernel, 85 % SDK and services, 80 % packs**, enforced in CI. Coverage is a floor, not a goal. |
| Real dependencies | `testcontainers` for PostgreSQL and Redis | Integration tests run against real Postgres and Redis, not mocks. Mocking a database is the fastest way to ship a broken query. |
| Property-based tests | `hypothesis` | Applied to manifest validation, event-envelope round-trips, config precedence resolution, and cost arithmetic. |
| HTTP tests | `httpx.AsyncClient` against the ASGI app | No live server needed. |
| Provider tests | Recorded-cassette fixtures for adapters + a small, explicitly-tagged live suite | Deterministic CI; live suite runs on demand, never gating the merge path. |
| Lint + format | `ruff` (lint, format, import order, `S`/bandit security rules) | One fast tool replacing flake8/black/isort/bandit. |
| Types | `mypy --strict` | Gating. |
| Dependency vulnerabilities | `pip-audit` against `uv.lock` | Gating on high/critical. |
| Secret detection | `gitleaks` | Gating. |
| Frontend | `vitest` (unit), `playwright` (end-to-end) | Dashboard only. |
| CI | **GitHub Actions** | `.github/workflows/ci.yml`. |

**Contract tests are the load-bearing part of this decision.** The SDK ships a reusable suite, `ai_os_sdk.testing.pack_contract_suite`, that every Capability Pack must run against itself. It validates the manifest against the JSON Schema, checks that every declared agent/tool/workflow resolves and matches its declared I/O schema, verifies no forbidden imports (no provider SDKs, no `ai-os-kernel` dependency), and asserts required permissions are declared. This turns "packs must comply with the contract" from prose into a test a pack either passes or fails.

**Test layering and the rule that keeps it honest:** unit tests (fast, no I/O) → contract tests → integration tests (real Postgres/Redis, real sandbox) → workflow tests (end-to-end with a stubbed Gateway) → regression tests. A bug fix requires a test that fails before the fix; the mandated tests exclude tests that only assert mock interactions, per the Coding Standards.

CI stages, fail-fast in order: lint/format → types → unit → contract → integration → security → build. Merges to the default branch require all stages green.

## Alternatives Considered

- **`unittest`** — Rejected: weaker fixtures and parametrisation; would slow every test author down for no gain.
- **Mocking Postgres and Redis in integration tests** — Rejected. The failures worth catching (transactional behaviour, `SKIP LOCKED` leasing, pgvector queries, migration correctness) are exactly the ones mocks hide.
- **`tox` / `nox` matrices** — Rejected as redundant given `uv`'s environment management plus a CI matrix.
- **GitLab CI / Jenkins / CircleCI** — Rejected: the repository's tooling already assumes GitHub, and `gh`-based workflows are already in use.
- **Coverage as the primary quality signal** — Explicitly rejected as a philosophy. Coverage is one gate among build, type, lint, security, and architecture-compliance gates.

## Consequences

### Positive
- Every mandated test class has a concrete home and runner.
- Pack compliance is machine-verified by a suite the pack author cannot skip.
- The platform's own gates use the same tooling the Software Engineering pack will run on generated code, so the gates are dogfooded.

### Negative
- Integration tests need Docker available locally and in CI, and are slower than mocked tests.
- Strict typing plus high coverage thresholds slow initial feature delivery.

### Neutral
- Live provider tests cost real money and are therefore opt-in and out of the merge path.

## Compliance

Complies with the Coding Standards (Testing Standards), the Quality Gates Framework, and the Capability Pack Contract testing requirements.

## References

- `docs/10_testing/test_strategy.md`
- `.github/workflows/ci.yml`
