# ai-os-kernel

The AI_OS Platform Kernel — the domain-agnostic runtime core. Owns orchestration, model
access, security, and observability. Contains **no domain-specific logic**; all business
logic lives in Capability Packs (`../capability_packs/`).

## Where to look first

| For | Read |
|---|---|
| What is built right now, and what is not | [`../docs/19_roadmap/feature_inventory.md`](../docs/19_roadmap/feature_inventory.md) |
| Per-module completion percentages | [`../docs/19_roadmap/feature_inventory.md`](../docs/19_roadmap/feature_inventory.md) |
| How to work in this repository | [`../CLAUDE.md`](../CLAUDE.md) |
| Everything else | [`../docs/DOCUMENTATION_INDEX.md`](../docs/DOCUMENTATION_INDEX.md) |

Architecture: [`../docs/03_architecture/kernel/kernel_architecture.md`](../docs/03_architecture/kernel/kernel_architecture.md)
Technology decisions: [`../docs/03_architecture/platform/technology_stack.md`](../docs/03_architecture/platform/technology_stack.md) and [`../docs/18_decision_log/README.md`](../docs/18_decision_log/README.md)

## Status

**Stage A process-complete (not exit-criteria-complete); Stage B well underway.** This is
no longer a skeleton — a four-agent software-engineering delivery pipeline runs end to end
through the real Workflow Engine, calling a real LLM Gateway and executing generated code
inside a real ADR-0016 Tier 1 Docker sandbox.

`feature_inventory.md` above is the authoritative,
maintained views. As a rough orientation only:

**Real, working subsystems** — `workflow_engine` (definition loading and validation,
instance lifecycle, event-sourced state, leases with a reaper, run-to-completion,
`workflow_steps`), `llm_gateway` (two provider adapters, router, dispatcher, circuit
breaker, backoff, error taxonomy, two budget scopes, capability negotiator, call
recorder), `persistence` (full schema across workflow/catalog/evaluation/governance/
platform/trace/knowledge, 29 Alembic migrations, keyword search over
`knowledge.chunks`), `sandbox` (`LocalSubprocessSandbox` and `DockerSandbox`, the latter
the config-driven default), `prompt_engine`, `context_manager`, `capability_manager`,
`security_manager`, `secrets_manager` (`env` backend), `configuration_manager`,
`observability`, `manifest_loader`, `health`, `routes`, `entrypoints`, `bootstrap.py`.

**Docstring-only stub packages, nothing built** — `evaluation_engine`, `event_bus`,
`knowledge_manager`, `memory_manager`, `quality_gate_engine`, `retrieval`,
`traceability_engine`. Each `__init__.py` explains what it will hold and which stage
fills it in.

## Layout

```text
src/ai_os_kernel/
├── bootstrap.py          Composition root — the only place the object graph is wired (ADR-0010)
├── prompted_completion.py  Prompt + Gateway composition used by pack agents
├── routes/               HTTP transport layer, no business logic: health.py, packs.py, workflows.py
├── entrypoints/          Process roles: api.py (FastAPI/Uvicorn), worker.py (ADR-0020)
└── <component>/          One subpackage per Kernel component (kernel_architecture.md)
alembic/                  Migrations (alembic.ini lives at the repository root)
```

There is no `settings.py` — runtime configuration lives in `configuration_manager/`
(`loader.py` plus `bootstrap_env.py` for the minimal `AIOS_*` bootstrap variables).

## Running locally

Everything runs from the **repository root**, not from this directory.

```sh
# 1. Install the workspace (Kernel + Software Engineering pack) into one venv
uv sync

# 2. Bring up the real dependencies (Postgres 16 with pgvector; Redis is started but
#    nothing in the Kernel uses it yet)
docker compose -f infra/docker-compose.yml --env-file .env up -d

# 3. Apply migrations
uv run alembic upgrade head

# 4. Run the API process role
uv run uvicorn ai_os_kernel.entrypoints.api:app --reload
```

Then:

```sh
curl http://127.0.0.1:8000/api/v1/health/live
curl http://127.0.0.1:8000/api/v1/health/ready
curl http://127.0.0.1:8000/api/v1/version
```

The worker process role is `ai_os_kernel.entrypoints.worker` — the same composition root,
a different entry point (ADR-0020). Note there is **no Dockerfile yet**, so the Kernel
itself is not containerised; Compose brings up dependencies only.

Environment variables actually read by Kernel code today (`AIOS_*` per ADR-0004; see
`.env.example` at the repository root for the full annotated list):

| Variable | Effect |
|---|---|
| `AIOS_ENV` | Selects the environment configuration layer: `local`, `dev`, `staging`, `production` |
| `AIOS_ROLE` | Which process role this instance runs: `api` or `worker` |
| `AIOS_DATABASE_URL` | Postgres connection; required for anything persistent |
| `AIOS_SANDBOX_BACKEND` | `docker` (default) or `local` — selects the Tier 1 sandbox backend |
| `AIOS_SECRET_BACKEND` | Selects the Secrets Manager backend (`env` is the only one built) |
| `AIOS_SECRET_LLM_ANTHROPIC_API_KEY` | Resolves `secret://env/llm/anthropic-api-key` |
| `AIOS_SECRET_SECURITY_JWT_SIGNING_KEY` | Resolves `secret://env/security/jwt-signing-key` |

## Testing

From the repository root:

```sh
uv run pytest tests/unit                 # fast, no I/O
uv run pytest tests/integration          # real Postgres via testcontainers; Docker required
uv run pytest                            # everything under tests/
uv run mypy --strict                     # config in the root pyproject.toml
uv run ruff check
```

Integration tests skip cleanly when no Docker daemon is reachable — Postgres-backed tests
must use `tests/integration/_postgres_fixture.py`'s `postgres_container()` rather than
constructing `PostgresContainer(...)` directly. Live provider tests (`*_live.py`) are
opt-in and skip without an API key. Current state: **849 passed, 11 skipped, 0 failed**,
with `mypy --strict` and `ruff` clean.

`tests/security/`, `tests/performance/`, `tests/regression/`, and `tests/benchmarks/` are
empty placeholder directories, and there is no `tests/contract/` — the ADR-0015 pack
contract suite does not exist yet because there is no `ai-os-sdk` to ship it.
