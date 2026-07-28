# ADR-0010: Composition and Dependency Injection — Explicit Composition Root, No DI Container

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/platform/platform_sdk.md`, `docs/03_architecture/kernel/kernel_architecture.md`

---

## Context

The Coding Standards mandate interface-driven design and dependency injection. AI_OS has roughly a dozen Kernel components with a dependency graph that must be initialised in a defined order (configuration and secrets first, then stores, then Gateway, then higher-level engines), shut down in reverse, and health-checked. Capability Packs must receive platform capabilities without gaining the ability to reach into Kernel internals.

## Decision

**Dependency injection by explicit constructor injection, wired in a single composition root. No DI framework or container.**

1. **Composition root** — `kernel/bootstrap.py` builds every component in a deterministic, explicit order and returns an assembled `Kernel`. Reading this one file tells you the entire object graph and startup order. Wiring is code, not decorator magic or runtime scanning.
2. **Constructor injection** — every component receives its collaborators as typed constructor parameters, each typed as a `Protocol` from `platform_sdk.contracts`. No component constructs its own dependencies, reads global state, or imports a singleton.
3. **Lifecycle protocol** — components needing setup/teardown implement `async def start()` / `async def stop()` / `async def health()`. The composition root starts them in dependency order and stops them in reverse, which is what makes graceful shutdown and readiness reporting correct rather than approximate.
4. **Pack-facing surface** — packs never see the `Kernel`. They receive a `PackContext` exposing only the SDK Protocols they are entitled to, narrowed by the permissions granted from their manifest. A pack cannot reach a capability it did not declare, because the object is not on the context it was handed.

## Alternatives Considered

- **A DI container (`dependency-injector`, `injector`, `punq`)** — Less wiring code; rejected because runtime-resolved graphs are harder to trace, defer errors from startup to first use, obscure initialisation order (which we specifically need to control), and add a dependency at the platform's foundation for a graph small enough to write out explicitly.
- **FastAPI's `Depends` as the platform DI mechanism** — Rejected: `Depends` is request-scoped and HTTP-bound. The Kernel must run identically under the API, the CLI, and a background worker. `Depends` is used only for HTTP request-scoped concerns (the current principal, the request-scoped security context), resolving the long-lived components from the already-composed Kernel.
- **Module-level singletons / service locator** — Rejected: untestable, hides coupling, and makes initialisation order implicit.
- **Passing the whole `Kernel` to packs** — Rejected: it would make every internal a de facto public API and destroy the boundary in [ADR-0001](ADR-0001-modular-capability-pack-architecture.md).

## Consequences

### Positive
- The entire dependency graph and startup order is readable in one file.
- Wiring errors surface at startup and are caught by `mypy --strict`, not at first request.
- Tests substitute fakes by passing them to constructors — no container configuration, no patching.
- The pack boundary is enforced by what is on the context object rather than by documentation.

### Negative
- The composition root grows as components are added and must be kept organised (grouped by layer, with the order commented).
- Adding a dependency means editing the root as well as the component — deliberate friction that keeps the graph visible.

### Neutral
- Request-scoped values still use FastAPI `Depends`; the two mechanisms have clearly separated scopes.

## Compliance

Complies with the Coding Standards (Interface-Driven Design, Dependency Injection) and [ADR-0004](ADR-0004-interface-driven-and-configuration-over-code.md).

## References

- `docs/03_architecture/platform/platform_sdk.md`
- `docs/03_architecture/kernel/health_lifecycle.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

`kernel/src/ai_os_kernel/bootstrap.py` is the single, explicit composition root — it wires the whole object graph in a deterministic order, builds the FastAPI app, and manages startup/shutdown through one lifespan handler, with constructor injection throughout and no DI container anywhere. The pack-facing surface exists but is reduced: `PackContext` (`capability_manager/pack_contract.py`) declares the intended shape including `health()`, while permission-narrowed capability handing and a uniform component `start()`/`stop()`/`health()` lifecycle protocol are not yet applied across all components.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
