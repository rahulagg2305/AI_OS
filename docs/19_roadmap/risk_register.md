# Risk Register — AI_OS

**Status:** Active, permanent · **Introduced:** Phase R2 (2026-07-31)

A real, permanent record of open risks. Hand-maintained (unlike the
generated roadmap views), but **entry-structured**: each risk is a fixed
row plus a short block. Never append narrative to an existing entry —
change its status field, or add a new entry.

Severity: **H** (can cause real harm or data loss) · **M** (can cause
significant rework) · **L** (contained).

| ID | Risk | Sev | Status | Owner decision |
|---|---|---|---|---|
| R-001 | Deploy capability shipping before the approval guardrail | H | **Open — hard rule** | Product owner, 2026-07-31 |
| R-002 | Docker exception-catching inconsistency across test guards | L | **Closed** 2026-07-31 | — |
| R-003 | CI integration job red on Linux, green locally | M | Open | Needs `gh auth login` |
| R-004 | `gh` CLI unauthenticated — CI logs unreadable | M | Open | Needs product-owner action |
| R-005 | Generated-doc staleness not yet gated in CI | M | Open | Scheduled P01-S06-M43-T05 |
| R-006 | 36 of 60 MUST requirements untouched | H | Open — accepted baseline | Product owner, 2026-07-31 |
| R-007 | `functional_requirements.md` status block drifts from reality | M | Mitigated 2026-07-31 | — |
| R-008 | No `AiOsError` hierarchy; error contract is per-module | M | Open | Scheduled P02-S07-M44-T01 |
| R-009 | Audit log is schema-only — no writer, no hash chain | H | Open | Scheduled P01-S05-M04-T05/T06 |
| R-010 | CI type-checks only a subset of `[tool.mypy] files` | M | Open | Found 2026-07-31 |
| R-011 | `ai_os_kernel` ships no `py.typed` marker | L | Open | Found 2026-07-31 |

---

### R-001 — Deploy capability before the approval guardrail

**Rule (permanent, product-owner decision 2026-07-31): no deployment
capability may ship before the Human Approval guardrail exists.**

`functional_requirements.md` §10 puts "autonomous production deployment
without human approval" out of v1 scope. Phase R1 found this currently
reads as satisfied only because *both* halves are missing: there is no
deploy capability (no Dockerfile, no Kubernetes, no Helm, no Terraform,
no Git integration) **and** no approval guardrail (FR-013/FR-111 at 0%;
`governance.approvals` has no writer; `human_approval` steps complete as
no-ops). `se.delivery_pipeline` already runs fully autonomously.

The moment either P07-S01-M40-T01 (Kubernetes/Helm) or P03-S01-M24-T01
(Git integration) lands without P03-S05-M14-T04/T05, this line flips
from satisfied to violated silently. **Blocking dependency:** those two
Tasks each declare the approval Tasks as `depends_on`.

### R-002 — Docker exception-catching inconsistency *(closed)*

`_postgres_fixture.py` caught only `docker.errors.DockerException`, while
`test_docker_sandbox_live.py` caught `(DockerException, OSError)`. A
connection *establishment* failure surfaces as a raw `OSError`, so the
narrower guard could have errored instead of skipping. Closed in Phase
R2 by widening the postgres fixture to match. Same root cause as the
`registry.py` fix of 2026-07-31.

### R-003 — CI integration job red on Linux, green locally

Run 30600653411: 6 of 8 jobs green; `Integration tests` fails. The exact
CI command reproduces **green** locally (989 passed, 12 skipped, coverage
96.93% against a 90% gate), so it is neither a coverage nor a test-logic
failure. Environment-specific to the Linux runner. Blocked on R-004.

### R-004 — `gh` CLI unauthenticated

`gh` v2.96.0 is installed but not logged in, so job logs return HTTP 403
and the R-003 cause cannot be read. Requires an interactive browser
device-code flow — see the Phase R2 report for the exact steps.

### R-006 — 36 of 60 MUST requirements untouched

Accepted as the real backlog baseline (product owner, 2026-07-31). By
phase: B=1, C=8, D=11, E=7, F=9. Tracked as Tasks; visible in
`STATUS.md`.

### R-010 — CI type-checks only a subset of the configured files

`ci.yml`'s mypy step runs `mypy --strict kernel/src kernel/alembic tests`
under a comment claiming it *"Mirrors [tool.mypy] files in pyproject.toml
exactly"*. It does not: the configured list also includes
`platform_sdk/src`, `platform_sdk/tests`,
`capability_packs/software-engineering/src`, that pack's `tests`, and
`scripts`. **None of those are type-checked in CI today** — a real hole
in the quality gate, and the comment is false. Found 2026-07-31 while
completing Phase R2. Not fixed in that step: changing what CI enforces
is its own approved change, not a mechanical completion item. The
canonical local invocation (`mypy --strict`, no arguments) does cover
all of them and passes — 370 source files.

### R-011 — `ai_os_kernel` ships no `py.typed`

`ai_os_sdk` and `ai_os_pack_software_engineering` both ship a `py.typed`
marker; `ai_os_kernel` does not. Consequence: any module importing
`ai_os_kernel` cannot be strictly type-checked *in isolation* — mypy
resolves it as an installed, untyped package and reports
`import-untyped`. It only passes when `kernel/src` is inside the same
analysis set. This is why `mypy --strict scripts tests/roadmap` fails
while `mypy --strict` succeeds. Low severity (the canonical invocation is
correct and green), but it makes per-directory type-checking misleading.

### R-009 — Audit log schema-only

`governance.audit_log` exists with no writer, no hash computed, and no
verification job, so FR-110 ("tamper-evident audit log") has no
implementation. Rated **H** because several governance claims elsewhere
implicitly assume it exists.
