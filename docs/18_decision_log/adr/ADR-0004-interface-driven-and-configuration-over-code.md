# ADR-0004: Interface-Driven Design and Configuration over Code

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`, `docs/03_architecture/kernel/configuration_manager.md`

---

## Context

AI_OS must survive the replacement of its most volatile parts — LLM providers, vector stores, storage backends, secret backends, event transports — without redesign. It must also allow behaviour to change per environment and per experiment without code changes, because controlled variation is a product requirement, not just an operational convenience.

## Decision

Two rules:

1. **Interface-driven.** Every replaceable dependency is consumed through an explicit interface (a `Protocol` in the chosen language — see [ADR-0008](ADR-0008-primary-language-and-runtime.md)) declared in the Platform SDK. Business logic depends on the interface; concrete adapters are selected at composition time.
2. **Configuration over code.** Model aliases, thresholds, timeouts, retry policy, feature flags, budgets, paths, and backend selection come from configuration, never from literals in code. Secrets are referenced by name and resolved at runtime ([ADR-0024](ADR-0024-secrets-management-backend.md)).

Both rules have a stated limit: an interface is justified when a second implementation is real or clearly imminent (provider adapters, stores, transports). Speculative interfaces with exactly one implementation and no prospect of a second are over-engineering and are not required.

## Alternatives Considered

- **Concrete classes with refactoring when a second implementation appears** — Less code today; rejected for the specific dependencies above because they change under production pressure, which is the worst time to discover the seam is missing.
- **Interfaces for everything** — Rejected: uniform indirection makes navigation harder and hides where variation actually exists.

## Consequences

### Positive
- Providers and backends are swappable; tests can substitute fakes at real boundaries.
- Environment and experiment variation is a configuration change, which keeps benchmarking runs honest.

### Negative
- One extra indirection at each seam.
- Configuration becomes a first-class artifact that must itself be schema-validated and audited.

### Neutral
- Requires a documented configuration precedence order, defined once in `docs/03_architecture/kernel/configuration_manager.md`.

## Compliance

Complies with the Project Constitution (Interface-Driven Design, Configuration over Code) and the Coding Standards.

## References

- `docs/03_architecture/platform/platform_sdk.md`
