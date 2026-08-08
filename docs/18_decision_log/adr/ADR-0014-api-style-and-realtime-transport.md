# ADR-0014: API Style and Real-Time Transport — FastAPI REST plus WebSocket

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/07_api/api_architecture.md`, `docs/13_dashboard/dashboard_architecture.md`

---

## Context

The Dashboard, CLI, Voice interface, and external integrations are all clients of a platform API that had never been specified, while three interface documents already depended on it. The API must serve request/response operations (start a workflow, approve a decision, query an experiment), stream live updates (workflow progress, log tails, agent activity), and remain consistent across channels so that no channel becomes a privilege-escalation path.

## Decision

**FastAPI, serving versioned REST over HTTP/1.1+HTTP/2 for operations and WebSocket for live streams.**

| Concern | Decision |
|---|---|
| Framework | FastAPI with Uvicorn. Chosen for native async, Pydantic v2 request/response models shared with the Kernel, and generated OpenAPI. |
| Style | Resource-oriented REST. Versioned prefix `/api/v1`. Breaking changes require a new major prefix and human approval ([ADR-0007](ADR-0007-human-governance-for-critical-decisions.md)). |
| Contract | OpenAPI 3.1 generated from the code and published; the generated document is the API contract and is snapshot-tested in CI so unintended contract drift fails the build. |
| Errors | RFC 9457 `application/problem+json`, with `type`, `title`, `status`, `detail`, `instance`, plus `trace_id` and the platform `error_code`. One error shape for the whole API. |
| Real-time | WebSocket at `/api/v1/stream`, with topic subscriptions (`workflow:{id}`, `experiment:{id}`, `approvals`, `system`). Server→client push carries the same versioned event envelope as the Event Bus, so the Dashboard consumes one event vocabulary. |
| Long operations | Always asynchronous: `202 Accepted` with a resource ID; progress via WebSocket or polling. No long-lived request blocking. |
| Pagination | Cursor-based (`cursor` + `limit`), returning `next_cursor`. Offset pagination is not used on event or log endpoints. |
| Idempotency | Mutating endpoints accept `Idempotency-Key`; replays return the original result. |
| Auth | OIDC bearer tokens for humans; API keys / service-account tokens for machines. Scopes map onto the permission model ([ADR-0023](ADR-0023-identity-roles-and-permissions.md)). Authorization is enforced in the Kernel, not the transport, so every channel enforces identically. |
| Rate limiting | Per-principal token bucket in Redis, applied at the API layer. |

**MCP is explicitly deferred and removed from the core API layer.** The single unexplained mention of MCP in the System Architecture is removed. Exposing AI_OS capabilities over MCP is attractive but is an *integration surface*, not core platform architecture; when needed it will be delivered as a Capability Pack that consumes the same public API, requiring its own ADR. This keeps the promise honest rather than aspirational.

GraphQL is likewise rejected rather than deferred silently: the Dashboard's needs are well served by purpose-built endpoints, and GraphQL would add schema-federation and query-cost concerns without addressing a real problem here.

## Alternatives Considered

- **gRPC** — Efficient and strongly typed; rejected because browsers require a proxy layer, and the Dashboard is a primary client. Not ruled out for future internal service-to-service traffic.
- **Server-Sent Events instead of WebSocket** — Simpler and adequate for one-way streaming, which is most of the need. Rejected because WebSocket also carries client→server messages (subscription changes, interactive approvals, future voice streaming) without a second mechanism.
- **Long polling** — Rejected: higher latency and worse resource behaviour at the concurrency targets in the NFR document.
- **Django REST Framework / Flask** — Rejected: synchronous-first, and would not share Pydantic models with the async Kernel.

## Consequences

### Positive
- One generated, testable contract serving Dashboard, CLI, Voice, and integrations.
- Request and response models are shared with the Kernel, eliminating a translation layer and a class of drift bugs.
- Uniform error shape and uniform authorization across every channel.

### Negative
- WebSocket connections are stateful and need connection-count limits, heartbeats, and back-pressure handling.
- API versioning discipline must be maintained from the first release.

### Neutral
- The API layer stays strictly transport-only: no business logic, per the System Architecture rule.

## Compliance

Complies with the System Architecture (no business logic in the API layer) and the Multi-modal Interaction Design (no channel privilege escalation).

## References

- `docs/07_api/api_architecture.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

FastAPI serves REST handlers under the decided `/api/v1` prefix, all with Pydantic v2 models shared with the Kernel. **Updated 2026-08-08 (`P06-S02-M37-T01`), correcting several other claims in this paragraph found stale in the same pass, not just adding the new item:** the WebSocket `/api/v1/stream` endpoint is now real — `ai_os_kernel.routes.stream`, real auth (the same token-verification/permission chain every REST route uses), real topic subscriptions mapped onto the real Event Bus's own fields (`workflow:{id}`/`system`/`approvals`; `experiment:{id}` refused, `Event` has no matching field), and a real, proven end-to-end delivery path — see `event_bus.md`'s own Implementation Status for the real gap this does not close (no Kernel component publishes to the bus in production yet). The RFC 9457 `application/problem+json` error shape is real (`ai_os_kernel.routes.problem_details.register_problem_detail_handlers`, wired in `bootstrap.py`). `Idempotency-Key` handling is real (`ai_os_kernel.routes.idempotency.IdempotencyKeyMiddleware`, also wired in `bootstrap.py`). The OpenAPI 3.1 snapshot test is real (`tests/contract/test_openapi_contract.py`). Not built: Redis-backed rate limiting (`RedisRateLimiter` exists but is never constructed in `bootstrap.py` — see `llm_gateway.md`'s own Implementation Status). MCP remains correctly absent.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
