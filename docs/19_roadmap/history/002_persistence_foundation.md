# AI_OS Implementation History — Persistence Foundation

**Milestone:** Stage B — the first real database schema and connectivity: `workflow_instances`/`workflow_events`/`workflow_leases`, Alembic migrations, and the Docker Compose Postgres/Redis dev environment. Schema and connectivity only — no Workflow Engine logic yet (that's `003_workflow_engine_core.md`).

Split out of the original single `implementation_status.md` on 2026-07-28 — content preserved verbatim. See `docs/19_roadmap/history/INDEX.md`.

---

### Stage B – Persistence Foundation (schema + connectivity only)
- **`infra/docker-compose.yml`**: Postgres 16 (`pgvector/pgvector:pg16`) + Redis 7 (`redis:7-alpine`) for local development, env-driven credentials with local-dev-only defaults, no api/worker services yet (no image exists).
- **`kernel/src/ai_os_kernel/persistence/`**: `DatabaseSettings` (`AIOS_DATABASE_URL`, env-only per configuration_management.md §3.3 — never a YAML value); `build_engine()` — SQLAlchemy 2.0 async Core engine (asyncpg), no ORM (ADR-0011); `schema.py` — Core `Table` definitions for `workflow_instances`, `workflow_events`, `workflow_leases`, column-for-column against `docs/08_database/data_model.md` §4.1/4.2/4.4.
- **Alembic**: root `alembic.ini` (`script_location = kernel/alembic`, no URL committed), async `env.py` reading `AIOS_DATABASE_URL` at run time, one baseline migration (`0001_workflow_state_baseline`) creating the `workflow` schema and its three tables, indexes, `CHECK` constraint on `status`, and the `UNIQUE (workflow_id, seq)` constraint.
- Two documented details deliberately deferred, not silently dropped (see `persistence/schema.py` docstring): the `workflow_events` UPDATE/DELETE revocation for "the application role" (no such DB role exists yet — no auth/role work has landed) and foreign keys to `catalog.workflow_definitions` / `evaluation.experiments` / `evaluation.run_manifests` (those schemas don't exist yet). Columns themselves are present exactly as documented.
- 4 new integration tests (`tests/integration/persistence/test_migrations.py`), real Postgres via `testcontainers` per `test_strategy.md` §2/§3.3 (ADR-0015 — no mocking the database): migration up → down → up round trip, documented-column/constraint verification, and two behavioral proofs (`UNIQUE (workflow_id, seq)` and the `workflow_leases → workflow_instances` foreign key both actually reject bad inserts).
- Verified twice: once via `pytest` against an ephemeral `testcontainers` Postgres, and once by hand against the committed `infra/docker-compose.yml` Postgres (`alembic upgrade head` / `downgrade -1` / `upgrade head`, `\dt workflow.*` confirming all three tables).
- `mypy --strict` (now also covering `kernel/alembic`), `ruff check`, `ruff format --check` all clean. Total suite: 33 tests passing (29 unit + 4 integration).
