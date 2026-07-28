# ADR-0018: Dashboard Technology Stack — React, TypeScript, Vite

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/13_dashboard/dashboard_architecture.md`, `docs/13_dashboard/information_architecture.md`

---

## Context

The Dashboard is the primary human interface: monitoring, approvals, experiment comparison, quality-gate results, cost, and log/trace investigation. It needs real-time updates, dense data tables, comparison views, and charts, and it is the one part of AI_OS that cannot reasonably be Python.

## Decision

| Concern | Decision |
|---|---|
| Language | TypeScript, `strict: true`. |
| Framework | React 19. |
| Build | Vite. |
| Routing | TanStack Router (type-safe routes). |
| Server state | TanStack Query — caching, revalidation, and request deduplication for REST reads. |
| Real-time | A single WebSocket connection to `/api/v1/stream`, with received events applied into the TanStack Query cache. One transport, one state store. |
| Styling | Tailwind CSS. |
| Components | shadcn/ui (Radix primitives) — copied into the repository rather than imported as a dependency, so components are ours to modify and audit. |
| Charts | Recharts. |
| Client generation | API client and types generated from the published OpenAPI 3.1 document; generation runs in CI and drift fails the build. |
| Tests | `vitest` for units, `playwright` for end-to-end flows (approve a decision, compare an experiment). |

**Architectural rule:** the Dashboard contains presentation and interaction logic only. No orchestration, no evaluation computation, no business rules. Anything it needs computed is computed by the platform and exposed through the API — otherwise the same logic would exist twice, in two languages, and diverge.

## Alternatives Considered

- **Server-rendered Python (FastAPI + Jinja + HTMX)** — Keeps the stack single-language and would have been attractive for a simpler product. Rejected because the Dashboard's hardest requirements — live multi-panel updates, side-by-side experiment comparison, interactive trace exploration — are where a client-side state model earns its cost.
- **Vue / Svelte** — Both technically fine. React chosen for the depth of available component ecosystem for data-dense interfaces and the larger body of reference material for AI-assisted continuation.
- **Next.js** — Rejected: server-side rendering and its server runtime add deployment surface for an authenticated internal tool that gains little from SSR.
- **A component library as a dependency (MUI, Ant Design)** — Rejected in favour of shadcn/ui's copy-in model, which avoids fighting an opinionated theme and keeps the component source reviewable.
- **Hand-written API client** — Rejected: guarantees drift from the OpenAPI contract.

## Consequences

### Positive
- Strong fit for real-time, data-dense views; type safety from API schema to component props.
- Generated client makes API contract drift a build failure.
- Component source is in-repo and auditable.

### Negative
- A second language and toolchain, with its own CI lane and dependency-audit surface.
- Requires frontend competence in a project otherwise centred on Python.

### Neutral
- The Dashboard is deployed as static assets behind the API gateway; it has no server runtime of its own.

## Compliance

Complies with the Dashboard Architecture (client of the platform, no embedded business logic) and [ADR-0014](ADR-0014-api-style-and-realtime-transport.md).

## References

- `docs/13_dashboard/monitoring_experiment_views.md`
