# ai-os-kernel

The AI_OS Platform Kernel — the domain-agnostic runtime core. Owns orchestration, model
access, security, quality gates, and observability. Contains **no domain-specific logic**;
all business logic lives in Capability Packs (`capability_packs/`).

Architecture: `docs/03_architecture/kernel/kernel_architecture.md`
Technology decisions: `docs/03_architecture/platform/technology_stack.md` and `docs/18_decision_log/`

## Status

**Stage A — Platform Skeleton.** Only the process entrypoints and health/version endpoints
are implemented. Every component subpackage below exists as a documented placeholder and is
filled in as its Implementation Roadmap stage arrives — see each `__init__.py` docstring.

## Layout

```text
src/ai_os_kernel/
├── settings.py           Runtime settings (env-driven; ADR-0004: configuration over code)
├── bootstrap.py          Composition root — the only place the object graph is wired (ADR-0010)
├── routes/               HTTP transport layer (no business logic — System Architecture)
├── entrypoints/          Process roles: api (FastAPI/Uvicorn), worker (ADR-0020)
└── <component>/          One subpackage per Kernel component (kernel_architecture.md)
```

## Running locally

From the repository root:

```sh
uv sync
uv run uvicorn ai_os_kernel.entrypoints.api:app --reload
```

Then: `curl http://127.0.0.1:8000/api/v1/health/live`

## Testing

```sh
uv run pytest tests/unit/kernel -v
uv run mypy --strict kernel/src
uv run ruff check kernel/src
```
