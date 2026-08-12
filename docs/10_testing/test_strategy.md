# Test Strategy – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Test Strategy
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Partially built — two documented test tiers are real and substantial; four directories are empty and one does not exist.**

**Built:** `tests/unit/` and `tests/integration/` — **849 passing, 11 skipped, 0 failing** as of this date. Integration tests use real Postgres via `testcontainers` and a real Docker daemon (no mocked database, per [ADR-0015](../18_decision_log/adr/ADR-0015-testing-and-ci.md)), through the shared `tests/integration/_postgres_fixture.py` helper that turns a missing daemon into a clean skip. Opt-in live-provider tests are gated on `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`. CI runs lint, types, unit, and integration for real.

**Not built:** `tests/security/` — Stage C requires it organised by threat ID, and it is **empty**, so no T1-T12 threat control has a dedicated regression test. `tests/performance/`, `tests/regression/`, and `tests/benchmarks/` are likewise **empty**, and **there is no `tests/contract/` directory at all**. CI's contract and security stages are therefore deliberately gated to no-ops. The 90% kernel coverage floor is met only when unit and integration are measured **together**.

One recorded exception to this strategy's own "real fakes, never mocks" rule: `tests/unit/kernel/sandbox/test_docker_executor.py` uses `unittest.mock` against the third-party `docker` SDK — see `../process/coding_standards.md` for the reasoning.

**A known flake family worth knowing about:** tests that stand up a real local HTTP server (`test_local_adapter.py`, `test_multi_provider_routing.py`, and `test_anthropic_adapter.py`'s error-classification cases) occasionally fail under full-suite load and pass in isolation. Three instances have been observed. Re-run in isolation before treating one as a regression.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md`. Build history: `../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines how AI_OS is tested: the layers, what belongs in each, the tooling, the CI pipeline, and the rules that keep the suite honest.

AI_OS has an unusual testing problem worth naming: it is a **non-deterministic system that must be tested deterministically**. The resolution is a hard boundary — the platform's own behaviour is deterministic and tested as such; model non-determinism is confined behind the LLM Gateway and stubbed in all tests except a small, non-gating live suite.

Governing decision: [ADR-0015](../18_decision_log/adr/ADR-0015-testing-and-ci.md).

---

## 2. Toolchain

| Concern | Tool |
|---|---|
| Runner | `pytest` + `pytest-asyncio` (strict mode) |
| Coverage | `pytest-cov`, branch coverage |
| Real dependencies | `testcontainers` (PostgreSQL 16 + pgvector, Redis 7) |
| Property tests | `hypothesis` |
| HTTP | `httpx.AsyncClient` against the ASGI app |
| Lint / format / security rules | `ruff` |
| Types | `mypy --strict` |
| Dependency CVEs | `pip-audit` |
| Secret scanning | `gitleaks` |
| Frontend | `vitest`, `playwright` |
| CI | GitHub Actions |

---

## 3. Layers

```text
tests/
├── unit/           fast, no I/O, no containers
├── contract/       SDK contract suite per pack + Protocol conformance
├── integration/    real Postgres, real Redis, real sandbox
├── workflow/       end-to-end workflows with a stubbed LLM Gateway
├── security/       organised by threat ID from the Security Architecture
├── performance/    load and latency against NFR targets
├── benchmarks/     cost and quality assertions
└── regression/     one test per fixed defect
```

### 3.1 Unit

Pure logic: state transitions, config precedence merging, cost arithmetic, RRF ranking, path canonicalisation, prompt rendering, permission intersection. No database, no network, no containers. Must complete in under 60 seconds for the whole suite.

### 3.2 Contract

Two kinds:

1. **Pack contract suite** — `ai_os_sdk.testing.pack_contract_suite`, which every Capability Pack must run and pass (nine checks listed in the Platform SDK Specification §9). This is what makes "packs comply with the contract" a testable claim rather than a documented hope.
2. **Protocol conformance** — every adapter is tested against the same shared test class for its Protocol. A `SecretProvider` implementation passes the same suite whether it is Vault, env, or the file backend. This is what makes the swappability claim in [ADR-0004](../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) real.

### 3.3 Integration

Real Postgres and real Redis via `testcontainers`, real container sandbox. Covers exactly the things mocks hide:

- Event-append and snapshot-update atomicity in one transaction
- `FOR UPDATE SKIP LOCKED` leasing under concurrency, and lease reclaim after simulated worker death
- Alembic migrations forward and backward against a seeded database
- pgvector HNSW queries and hybrid RRF ranking
- Outbox write-and-relay, including crash between commit and dispatch
- Tier 1 sandbox containment: no network, no secrets, resource limits enforced
- Audit hash-chain continuity and break detection

### 3.4 Workflow (end-to-end)

Full workflows with a **stubbed LLM Gateway** returning recorded, deterministic responses. Real Workflow Engine, real state, real gates, real sandbox, real approval flow. Covers:

- A complete sequential workflow to `completed`
- A blocking gate failure halting progression
- A Human Approval Point pausing, persisting, and resuming on decision
- Retry, compensation, and escalation paths
- Parallel and `foreach` fan-out with per-workflow workspace isolation
- Budget exhaustion mid-workflow

### 3.5 Security

Organised by threat ID (`test_t01_sandbox_containment.py`, `test_t05_privilege_narrowing.py`, …) so coverage of the threat model is directly visible. Each numbered threat's primary control has at least one test asserting the control holds, including negative tests that assert an attempted violation fails.

### 3.6 Performance and benchmarks

Nightly, not on the merge path. Asserts the NFR targets in `../02_requirements/non_functional/nfr.md` and fails on regression beyond a tolerance band rather than on absolute noise.

### 3.7 Regression

Every fixed defect gets a test that fails before the fix. Named with the defect reference.

---

## 4. Rules

1. **A bug fix requires a failing test first.** No exceptions.
2. **Do not test mocks.** A test whose only assertions are on mock call arguments, with no behavioural assertion, is rejected in review. This is stated in the Coding Standards and enforced by reviewers.
3. **Do not mock what you own at a real boundary.** Postgres, Redis, and the sandbox are used for real in integration tests. Only genuinely external, costly, non-deterministic dependencies (model providers, speech providers, remote Git hosts) are stubbed.
4. **Tests are deterministic.** No wall-clock sleeps, no random seeds without pinning, no dependence on test execution order. Time is injected.
5. **Tests are isolated.** Each test gets a fresh schema or a transactional rollback. No shared mutable fixtures.
6. **Coverage is a floor, not a goal.** Meeting the threshold with tests that assert nothing meaningful is worse than being under it honestly.
7. **Live provider tests are opt-in and never gate a merge.** They cost money and are non-deterministic; they run on demand to validate adapters against reality.

---

## 5. Testing Non-Deterministic Behaviour

| What | How |
|---|---|
| Platform logic | Deterministic; tested by exact assertion |
| Model responses | Stubbed Gateway with recorded responses; the stub is a Protocol implementation, so it is type-checked |
| Provider adapters | Recorded cassettes for the request/response shape; a small live suite for reality checks |
| Agent output handling | Test the platform's handling of well-formed, malformed, refused, truncated, and injected-instruction outputs — the platform's behaviour on each is deterministic and must be asserted |
| Quality gate evaluation | Deterministic given inputs; tested with fixture artifacts |
| Comparison reporting | Tested with synthetic multi-run data asserting correct mean and variance computation, and correct exclusion of cache-served runs |

Note what this yields: we never assert that a model produces particular content. We assert that the platform behaves correctly for every class of content a model might produce — including hostile content.

---

## 6. CI Pipeline

```text
lint      ruff check · ruff format --check
types     mypy --strict
unit      pytest tests/unit
contract  pytest tests/contract
integration  pytest tests/integration        (testcontainers)
workflow  pytest tests/workflow
security  pytest tests/security · pip-audit · gitleaks
build     docker build · uv sync --frozen verification
frontend  vitest · tsc --noEmit · playwright (on dashboard changes)
```

Fail-fast in order. All stages must pass to merge to the default branch. Nightly adds `performance` and `benchmarks`. Coverage thresholds (NFR-060 to NFR-062) are enforced in the relevant stages.

---

## 7. Test Data

- Fixtures live in `tests/fixtures/`, are version-controlled, and are small.
- Sample repositories for Project Intelligence tests are checked in as fixtures or vendored as pinned archives — never cloned from the network during a test.
- **No real credentials, ever.** Secret-related tests use the env or file backend with synthetic values.
- Recorded provider responses are redacted before commit and are reviewed for accidental content.

---

## 8. Quality Gates for Generated Software

The Software Engineering Pack runs gates on the software AI_OS produces, using the same tools listed in §2 where the target language allows. The gate set and thresholds are configuration per project, defaulting to the values in NFR-063 onward. This is deliberate dogfooding: the platform's own gates and the gates it applies to its output are the same code path.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution
2. Coding Standards & Best Practices
3. Quality Gates Framework
4. Architecture Decision Records
5. Test Strategy (this document)
6. Source Code
