# Coding Standards (Working Summary) – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28

**This is a pointer and a curated highlight reel, not a second authority.** The full, Mandatory standard is `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` — read it for anything not covered below, and defer to it on any conflict. This file exists only to surface the handful of rules that have actually mattered, repeatedly, in how this codebase has been built so far, so a session doesn't have to re-derive them.

---

## The rules that have actually mattered in practice

- **Interface-driven, but only when it's earned (ADR-0004).** A `Protocol` is justified when a second real implementation is real or clearly imminent (e.g. `SandboxExecutor` → `LocalSubprocessSandbox` + `DockerSandbox`). A Protocol with exactly one implementation and no real second one coming is over-engineering. This has been invoked repeatedly to justify duplicating small helper functions across agent modules instead of extracting a shared abstraction prematurely — and, in the opposite direction, to justify the shared `tests/integration/_postgres_fixture.py` helper once ~30 real, identical call sites existed.
- **Explicit composition root, no DI container (ADR-0010).** Everything is wired in `kernel/bootstrap.py` (or, for a Capability Pack, its own pipeline/pack composition module). No service locator, no module-level singleton.
- **No hardcoded configuration.** Named module-level constants with a comment explaining they're a "first-cut, not yet tuned" default are fine and used throughout; a bare magic literal buried in a function body is not.
- **No hardcoded secrets, ever.** Secrets are `secret://` references resolved through a `SecretProvider`, never embedded, never logged, never passed into a sandbox.
- **`mypy --strict` and `ruff check`/`ruff format --check` clean is the bar for "done."** Every step in this project's history has run this sweep before reporting completion. A per-module `[[tool.mypy.overrides]]` (e.g. for an untyped third-party library like `docker`) is acceptable when scoped narrowly and commented; a project-wide suppression is not.
- **Real tests over mocks — this is the default, not a preference.** Every Protocol this project owns gets a real, deterministic implementation in tests (an `Echo*`, an `InMemory*`, a fake repository) rather than a mock. The one recorded exception: `tests/unit/kernel/sandbox/test_docker_executor.py` uses `unittest.mock` against the third-party `docker` SDK, because that class is not owned by this project and cannot be meaningfully faked in-process — and it is paired with a second, real, unmocked integration suite (`tests/integration/sandbox/test_docker_sandbox_live.py`) that proves the actual guarantee. If you find yourself reaching for a mock, check first whether a real fake or a real execution path is actually available — it usually is.
- **No placeholder/speculative architecture.** Don't build a capability "because it'll probably be needed later." Build the smallest real slice the current approved step asks for, and record what's still missing rather than stubbing it out.
- **Report discovered gaps; don't silently work around them.** When an approved step's own scope collides with something undocumented, underspecified, or inconsistent (a manifest schema gap, a naming mismatch, a stale doc), the established pattern is: resolve it with the smallest defensible fix, and *record* the discovery and the reasoning — in the module's own docstring and in `implementation_status.md` — rather than quietly patching around it.
- **Documentation is the source of truth, and it gets updated in the same step as the code.** Every implementation step in this project's history has ended with `implementation_status.md` updated before the step is considered done.

## Naming conventions actually in use

Pulled directly from the full standard — see it for the complete table:

| Element | Convention | Example |
|---|---|---|
| Modules/packages | `snake_case` | `llm_gateway`, `sandbox` |
| Classes | `PascalCase` | `DockerSandbox`, `WorkflowStepOutputResolver` |
| Protocols | `PascalCase`, no `I` prefix | `SandboxExecutor`, `ContextSourceResolver` |
| Functions/methods | `snake_case`, verb-first | `resolve_agent`, `assemble` |
| Constants | `UPPER_SNAKE_CASE` | `_DEFAULT_IMAGE`, `_MAX_OUTPUT_TOKENS` |
| Private | leading underscore | `_extract_payload` |
| Pack/agent ids | `kebab-case` | `software-engineering`, `qa-test` |
| Workflow/gate/tool ids | dot-namespaced lower snake | `se.delivery_pipeline`, `build.write_file` |

**Agent-id naming has one real, recorded precedent worth knowing about**: the reprioritization's own four agents (`architecture`, `build`, `qa-test`, `documentation`) were originally named informally (`architect`, `test`) and drifted from `docs/06_capability_packs/software_engineering/agents.md`'s own Approved catalog before being reconciled in a dedicated step. When adding a new agent to an existing Capability Pack, check that pack's own documented Agent Catalog *first* — don't invent a slug and reconcile it later.
