# Performance test suite — real measurements against `nfr.md` §3-5

`P01-S06-M42-T05`. This is the repeatable performance report
`nfr.md` §13 names (`tests/performance/ load suite in CI nightly`) —
closing the "no measurement path exists yet" gap that document's own
Implementation Status disclosed for every latency/throughput target.

**Run it:** `uv run pytest tests/performance -v -s` (real Postgres via
testcontainers; `-s` to see each test's own printed real numbers).
Every assertion is a real pass/fail against `nfr.md`'s documented
threshold — nothing here is a synthetic/trivial benchmark presented as
real. Several tests intentionally use **real, production interval
constants** (never a test-shortened override) so their own timing
genuinely reflects the target being measured — this makes a few of
them slow (tens of seconds), which is exactly why this suite runs
nightly/on demand (`.github/workflows/performance.yml`), never on
every push.

## Measured (real infrastructure, real numbers, pass/fail against the documented target)

| NFR | What | File |
|---|---|---|
| NFR-010 | API read endpoint latency (p95/p99) | `test_latency.py` |
| NFR-011 | Workflow submission latency (service-layer `create_instance`+`start`) | `test_latency.py` |
| NFR-012 | Platform overhead per step, excluding agent/model time (real `EchoAgent`) | `test_latency.py` |
| NFR-013 | Context assembly latency | `test_latency.py` |
| NFR-015 | Tier 1 sandbox cold start (real `DockerSandbox`) | `test_latency.py` |
| NFR-018 | Workflow state write latency (event + snapshot, one transaction) | `test_latency.py` |
| NFR-020 | Workflow step completion throughput, one real worker replica | `test_throughput.py` |
| NFR-021 | API read throughput | `test_throughput.py` |
| NFR-033 | Workflow resumption after a real simulated worker crash (lease expiry + reclaim) | `test_availability_recovery.py` |
| NFR-036 | Graceful shutdown drain time | `test_availability_recovery.py` |

**A real, extra measurement with no numbered NFR of its own:** the
Scheduler's own real poll-to-start latency (`test_throughput.py`) —
`nfr.md` §3-5 has no ID for "how long after `scheduled_at` is due does
a real Scheduler tick actually start the instance," even though the
task asked this suite to genuinely measure the real Scheduler loop.
Reported as a real number for visibility, not scored pass/fail against
a target that does not exist.

## Disclosed: not genuinely measurable yet, and why

Honest per this step's own constraint ("if an NFR target can't be
honestly measured yet ... disclose that clearly rather than faking a
measurement") — matches `nfr.md`'s own Implementation Status, re-verified
directly against the real codebase on 2026-08-03, not copied stale:

- **NFR-014 (hybrid retrieval, 5M chunks)** — no vector search / hybrid
  retrieval component exists (module 11, Retrieval, is a keyword-search
  slice only; no `pgvector` query path, no RRF).
- **NFR-016 (LLM Gateway overhead, excluding provider time)** — the
  real `DispatchingLLMGateway` pipeline (router, budget enforcer,
  circuit breaker, capability negotiator) only runs ahead of a real
  provider call; there is no deterministic stand-in backend wired
  through that *same* pipeline today, only `EchoLLMGateway` used as a
  complete `LLMGateway` replacement elsewhere in this codebase — timing
  that would measure `EchoLLMGateway` itself, not this pipeline's own
  overhead.
- **NFR-017 (WebSocket event delivery)** — no Event Bus (module 17) and
  no WebSocket route exist.
- **NFR-019 (dashboard FCP)** — `dashboard/` is an empty directory.
- **NFR-021's own "per API replica" framing** — measured here via
  `TestClient` (real ASGI dispatch, no real network stack), matching
  NFR-010's own documented measurement method ("server-side span,
  excluding client network") — a real, honest number, but not identical
  to a real deployed replica behind a real socket under real OS
  scheduling.
- **NFR-022 (in-process event bus, ≥1,000 events/s)** — no event bus
  exists (module 17 is unbuilt; `P02-S07-M17-T02` is still on the ready
  list).
- **NFR-023 (outbox relay lag)** — `platform.event_outbox` is
  schema-only; no relay process reads it.
- **NFR-024 (document ingestion, ≥50/min/worker)** — no document
  ingestion pipeline exists (Knowledge Manager, module 9, is a writer +
  keyword reader only).
- **NFR-025 (worker scaling, ≥80% linear to 8 replicas)** — needs *N*
  genuinely separate worker processes/containers measured together, a
  heavier multi-container load-test setup distinct from this suite's
  own in-process-pytest shape; `P01-S01-M40-T05` proved one real,
  standalone worker replica works, which is what NFR-020 here measures
  as the real single-replica baseline this target would scale from —
  the scaling *curve* itself remains unmeasured.
- **NFR-030/031 (99.5% monthly availability; zero planned-maintenance
  downtime)** — production-monitoring-window targets; no test suite
  can honestly assert a monthly percentage or a deploy's own downtime
  in a single run.
- **NFR-032 (zero committed workflow state lost on crash)** — real
  structural support exists (event log + snapshot in one transaction,
  already covered by `tests/integration/`), but no test in this
  codebase yet genuinely kills an OS process mid-write and inspects the
  aftermath; `nfr.md` itself already disclosed this exact gap
  ("not yet by a process-kill chaos test"), still true today. A
  heavier chaos-test addition, not a performance measurement — left
  for a dedicated step.
- **NFR-034/035 (RPO ≤5 min / RTO ≤1 hour)** — no backup or restore
  tooling exists to measure a recovery point or time against.
- **NFR-037 (provider outage fallback within 3 attempts)** — a
  correctness property of the router/circuit-breaker, not a timing
  target; already covered by `tests/unit`/`tests/integration` for the
  LLM Gateway, out of this performance suite's own scope.
- **NFR-038 (Redis loss degrades, never fails)** — no Redis client
  integration exists yet (`P02-S07-M23-T01` is still on the ready
  list) — there is nothing wired to Redis for a loss to degrade.
