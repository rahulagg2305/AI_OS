# API Architecture – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** API Architecture
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-03, `P03-S03-M30-T06`; RFC 9457 error bodies added 2026-08-06, `P06-S01-M36-T02`; Idempotency-Key handling added 2026-08-06, `P06-S01-M36-T03`)

**Partially built — roughly 10 of the ~45 endpoints documented below exist.** Read this section before assuming an endpoint is callable.

**Built** (`kernel/src/ai_os_kernel/routes/`, all bearer-token authenticated): `POST /api/v1/workflows`, `GET /api/v1/workflows`, `GET /api/v1/workflows/{id}`, `GET /api/v1/workflows/{id}/steps`, `GET /api/v1/workflows/{id}/events`, `POST /api/v1/packs`, `POST /api/v1/packs/{id}/activate`, `POST /api/v1/packs/{id}/deactivate`, `GET /api/v1/packs/{id}`, plus the health endpoints.

**§8's own RFC 9457 error shape is now real (2026-08-06, `P06-S01-M36-T02`) — every route's own error, uniformly, not a per-route migration.** `ai_os_kernel.routes.problem_details.register_problem_detail_handlers` installs three real FastAPI exception handlers on the app: `HTTPException` (every current raise site, confirmed by direct inspection — no route raises anything else today), FastAPI's own automatic `RequestValidationError` (422, with a real `violations` array), and a catch-all `Exception` (500, `trace_id` always present via the same per-request id `TraceIdMiddleware` already binds, and the real exception's own message never reaches the response — §8's "never include secrets, stack traces, SQL, or internal paths"). **`error_code`/`type`/`title` are honestly coarse, not the rich, per-route values this section's own example below shows (`"workflow.not_found"`)** — derived from the HTTP status code alone (§8's own status table, verbatim), since no route today raises anything carrying a real, specific code to report; `StructuredError.error_code`'s own docstring already discloses why ("the catalogue itself does not exist yet"). Migrating individual routes onto `ai_os_sdk`'s own `AiOsError` hierarchy so each could report its own real, specific code is real, disclosed, separate follow-up work, not attempted here.

**§6.2 Approvals — one real endpoint now exists, at a genuinely different shape than documented below (`P03-S03-M30-T06`), not a silent reconciliation.** `POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions` (`ai_os_kernel.routes.approvals`) — nested under its own workflow, plural `decisions`, versus this section's own designed `POST /api/v1/approvals/{id}/decision`. Two real, disclosed deviations from the design below: (1) authorization is the real, shipped `approver:<approval_class>` **role** (ADR-0023, `security_manager.approval_authorization`), not the `approval:decide:<class>` **permission** §6.1's table below documents — `permissions.py`'s own real, deliberately-reduced flat permission model cannot express a permission family parameterized by an arbitrary class any more than it can a role family (see that module's own docstring, and `security_manager.md`'s Implementation Status for the concrete request that proved this); (2) idempotency ("a second identical decision returns the original result") is **partially real as of `P06-S01-M36-T03`** — a caller sending a real `Idempotency-Key` header now genuinely gets the cached original response for an identical replay (`ai_os_kernel.routes.idempotency.IdempotencyKeyMiddleware`, generic across every mutating route, not approvals-specific); without that header, `ApprovalService.decide()`'s own business logic is unchanged — a second `decide()` against an already-decided approval still returns `409` unconditionally (`ApprovalNotPendingError`), regardless of whether the payload matches. `GET /approvals`, `GET /approvals/{id}`, `GET /approvals/history` remain genuinely not built.

**§9's own `Idempotency-Key` handling is now real too (2026-08-06, `P06-S01-M36-T03`), generically across every mutating route, not one at a time.** `ai_os_kernel.routes.idempotency.IdempotencyKeyMiddleware` — a real ASGI middleware (registered in `build_app`, the same "sees both the request and the eventual response" shape `TraceIdMiddleware` already establishes), backed by the real, previously-schema-only `platform.idempotency_keys` table. A replay (identical key, identical method+path+body, identical principal) returns the original response verbatim; a reused key with a different body **or a different principal** returns a real `409` problem+json body (the principal check is a real, deliberate extension beyond §9's own literal words — `idempotency.py`'s own module docstring explains why). An unauthenticated request is never idempotency-handled (no principal to key the store's own required column on) — passed straight through so `authenticate`'s own dependency still refuses it normally. **One real, disclosed, narrow race window**: two concurrent requests presenting the identical, brand-new key can both pass the "not yet stored" check before either commits its own row; the store's own `INSERT ... ON CONFLICT DO NOTHING` means only the first write wins the stored row, and the losing request still returns its own, locally-computed response rather than the winner's — not solved with distributed locking, which this step's own scope did not call for.

**Not built:**
- **The entire WebSocket stream** (`/api/v1/stream`) — no route, no topics, no event envelope. Every real-time feature specified here and in `../13_dashboard/` has no transport.
- All Experiments, Gates, Usage, Agents, Config, Traceability, and Logs/Traces endpoint groups, and the remaining 3 of 4 Approvals endpoints above — each blocked on a subsystem that is itself 0% built (Evaluation Engine, Quality Gate Engine, Traceability Engine) or simply not yet built (Approvals listing/history).
- **The `error_code` catalogue** — RFC 9457 error *bodies* are now real (above); the stable, per-domain `error_code` values §3/§4.4 of `platform_sdk.md` describe (e.g. `"workflow.not_found"`) still do not exist as a populated catalogue, so every code reported today is the coarser, status-derived one.
- **Per-principal rate limiting** — requires Redis, which no Kernel code uses.
- **Cursor pagination** on `/steps` and `/events` (they return unpaginated), and filtering on the workflow list.
- **The generated OpenAPI 3.1 contract and its CI snapshot test.** FastAPI serves a schema, but it is neither snapshot-tested nor verified against this document, so drift is currently undetected.

Deliberate documented divergences in what *is* built: `POST /api/v1/workflows` returns `200` with a reduced body rather than `202` with `definition_id`; pack activate/deactivate return `200` not `202`; `POST /api/v1/packs` is not in this document's endpoint list at all (a reasoned addition). Stage B/F deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document specifies the AI_OS platform API: the HTTP surface, the real-time stream, authentication, authorization, error format, and versioning rules. The Dashboard, CLI, Voice interface, and external integrations are all clients of this API and of nothing else.

Governing decision: [ADR-0014](../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md).

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Platform SDK Specification

---

## 2. Principles

1. **The API is transport only.** No business logic, no orchestration decisions, no evaluation computation. It authenticates, authorizes, validates, and delegates to the Kernel.
2. **All channels are equal.** Dashboard, CLI, Voice, and integrations use the same endpoints and get the same authorization decisions. Authorization is enforced in the Kernel, so no channel can be a privilege-escalation path.
3. **Contract-first in effect.** The OpenAPI 3.1 document is generated from code, published at `/api/v1/openapi.json`, and snapshot-tested in CI; unintended contract drift fails the build.
4. **Long work is always asynchronous.** No request blocks on a workflow.
5. **Consistent shapes.** One error format, one pagination style, one event envelope.

---

## 3. Base and Versioning

```text
Base path:  /api/v1
Media type: application/json (requests and responses)
Errors:     application/problem+json  (RFC 9457)
Streaming:  WebSocket at /api/v1/stream
Contract:   GET /api/v1/openapi.json
```

- **Additive changes** (new endpoint, new optional field, new enum value a client may ignore) ship within `v1`.
- **Breaking changes** require `/api/v2`, a deprecation period during which both are served, and human approval ([ADR-0007](../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).
- Clients must tolerate unknown response fields.

---

## 4. Authentication

| Principal | Mechanism | Header |
|---|---|---|
| `user` | OIDC bearer token (access token from the configured identity provider) | `Authorization: Bearer <jwt>` |
| `service_account` | Platform-issued API key or OIDC client credentials | `Authorization: Bearer <token>` |
| `agent` | **Never authenticates to the API.** Agents run inside workflows and derive authority from the workflow's security context ([ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)) | — |

Unauthenticated access is denied for every endpoint except `/api/v1/health/live`, `/api/v1/health/ready`, and `/api/v1/openapi.json`.

Token validation checks signature, issuer, audience, and expiry. The resulting principal, roles, and effective permissions are assembled into a `SecurityContext` that travels with the request and is the sole basis for authorization decisions.

---

## 5. Authorization

Every endpoint declares the permission it requires. The API layer refuses a request whose principal lacks that permission with `403` and an audited authorization-denied record. Endpoint-level checks are a first filter, not the only one: the Kernel re-checks at the point of action, so a bug in the transport layer cannot grant authority.

| Permission | Grants |
|---|---|
| `workflow:read` | Read workflow instances, steps, results |
| `workflow:start` | Submit a workflow |
| `workflow:control` | Cancel, retry, resume |
| `approval:read` | See pending approvals |
| `approval:decide:<class>` | Decide an approval of that class (for example `approval:decide:release`) |
| `experiment:read` / `experiment:run` | Read / launch experiments |
| `pack:read` / `pack:manage` | Read / install, activate, deactivate packs |
| `config:read` / `config:write` | Read / change non-security configuration |
| `secret:manage` | Manage secret references (admin only) |
| `telemetry:read` | Read logs, traces, metrics |

---

## 6. Resources

### 6.1 Workflows

```text
POST   /api/v1/workflows                     Start a workflow          → 202
GET    /api/v1/workflows                     List (cursor-paginated)   → 200
GET    /api/v1/workflows/{id}                Instance detail           → 200
GET    /api/v1/workflows/{id}/steps          Step history              → 200
GET    /api/v1/workflows/{id}/events         Event log (cursor)        → 200
GET    /api/v1/workflows/{id}/run_manifest   Reproducibility manifest  → 200
POST   /api/v1/workflows/{id}/cancel         Request cancellation      → 202
POST   /api/v1/workflows/{id}/retry          Retry from last failure   → 202
GET    /api/v1/workflow_definitions          Registered definitions    → 200
```

`POST /workflows` accepts `definition_id`, `definition_version` (optional; latest if omitted), `inputs`, and optional `experiment_id`. It returns `202` with the instance ID and does not wait. `Idempotency-Key` is honoured.

`run_manifest` returns the complete pinned-conditions bundle required by [ADR-0022](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md).

### 6.2 Approvals

```text
GET    /api/v1/approvals                     Pending approvals         → 200
GET    /api/v1/approvals/{id}                Detail incl. decision context → 200
POST   /api/v1/approvals/{id}/decision       Approve/reject/changes    → 200
GET    /api/v1/approvals/history             Past decisions            → 200
```

`POST .../decision` body: `decision` (`approve` | `reject` | `request_changes`), optional `comment`. The principal must hold `approval:decide:<class>` for that approval's class. The decision, principal, timestamp, and the context digest shown at decision time are written to the audit log. Decisions are idempotent — a second identical decision returns the original result; a conflicting one returns `409`.

### 6.3 Experiments

```text
POST   /api/v1/experiments                   Define an experiment      → 201
GET    /api/v1/experiments                   List                      → 200
GET    /api/v1/experiments/{id}              Detail + run status       → 200
POST   /api/v1/experiments/{id}/run          Launch runs               → 202
GET    /api/v1/experiments/{id}/comparison   Comparison report         → 200
GET    /api/v1/experiments/{id}/runs         Per-run detail            → 200
```

The comparison report includes, per model, aggregate metrics **with variance across repeated runs**, and flags any run where `served_from_cache` is true (such runs are excluded from aggregates, per [ADR-0025](../18_decision_log/adr/ADR-0025-caching-strategy.md)).

### 6.4 Quality, cost, agents

```text
GET    /api/v1/gates/results                 Gate results (filterable) → 200
GET    /api/v1/gates/trends                  Pass/fail over time       → 200
GET    /api/v1/usage/cost                    Cost by model/workflow/pack → 200
GET    /api/v1/usage/tokens                  Token usage incl. cache split → 200
GET    /api/v1/agents                        Registered agents + stats → 200
```

### 6.5 Packs and configuration

```text
GET    /api/v1/packs                         Installed packs + state   → 200
GET    /api/v1/packs/{id}                    Detail + health           → 200
POST   /api/v1/packs/{id}/activate           Activate                  → 202
POST   /api/v1/packs/{id}/deactivate         Deactivate                → 202
GET    /api/v1/config                        Effective config (secrets redacted) → 200
PATCH  /api/v1/config                        Update non-secret values  → 200
GET    /api/v1/config/flags                  Feature flags             → 200
```

Pack activation that changes platform behaviour requires human approval and returns `202` with an approval reference.

### 6.6 Traceability and observability

```text
GET    /api/v1/traceability/query            Query the link graph      → 200
GET    /api/v1/traceability/impact/{id}      Impact analysis           → 200
GET    /api/v1/traceability/coverage         Gaps (e.g. reqs w/o tests) → 200
GET    /api/v1/logs                          Search logs by correlation ID → 200
GET    /api/v1/traces/{trace_id}             Trace detail              → 200
```

### 6.7 Health

```text
GET    /api/v1/health/live                   Liveness (unauthenticated) → 200
GET    /api/v1/health/ready                  Readiness (unauthenticated) → 200|503
GET    /api/v1/health/detail                 Component + pack health    → 200
```

`ready` returns `503` until the Kernel reports `Ready`. It never reports ready while a critical component is failed — a degraded-but-serving Kernel reports `200` with `status: degraded`.

---

## 7. Real-Time Stream

```text
WS /api/v1/stream
```

Authenticated by bearer token in the connection request. On connect the server sends `{"type":"connection.ready","protocol_version":1}`.

**Client → server**

```json
{"type": "subscribe",   "topics": ["workflow:wf_01H…", "approvals"]}
{"type": "unsubscribe", "topics": ["workflow:wf_01H…"]}
{"type": "ping"}
```

**Server → client** — the same versioned envelope used by the Event Bus, so the Dashboard consumes one event vocabulary:

```json
{
  "event_id": "evt_01H…",
  "event_type": "workflow.step.completed",
  "schema_version": 1,
  "timestamp": "2026-07-25T10:31:00Z",
  "topic": "workflow:wf_01H…",
  "trace_id": "…",
  "payload": { }
}
```

Topics: `workflow:{id}`, `experiment:{id}`, `approvals`, `packs`, `system`. Subscription is authorized per topic; subscribing to a topic the principal cannot read returns an error frame and no events.

Operational rules: server heartbeat every 30 s and clients must respond; per-connection subscription cap and per-principal connection cap from configuration; a client that cannot keep up has its slowest topic dropped with a `stream.lagged` frame rather than being allowed to consume unbounded server memory. **The stream is not a durable log** — clients reconcile gaps by re-reading `GET /workflows/{id}/events`, which is authoritative.

---

## 8. Errors

RFC 9457, one shape everywhere:

```json
{
  "type": "https://ai-os.dev/problems/workflow-not-found",
  "title": "Workflow not found",
  "status": 404,
  "detail": "No workflow instance with id wf_01H…",
  "instance": "/api/v1/workflows/wf_01H…",
  "error_code": "workflow.not_found",
  "trace_id": "0af7651916cd43dd8448eb211c80319c"
}
```

`error_code` is the stable, catalogued platform code from the SDK error model; `type` and `title` are for humans. Validation failures add a `violations` array (`field`, `message`).

| Status | Meaning | Notes |
|---|---|---|
| 400 | Malformed request | |
| 401 | Unauthenticated | |
| 403 | Authorized principal lacks the permission | Audited |
| 404 | Not found, or not visible to this principal | Deliberately indistinguishable |
| 409 | State conflict | e.g. conflicting approval decision |
| 422 | Semantically invalid | Schema violation |
| 429 | Rate limited | `Retry-After` header |
| 500 | Internal error | `trace_id` always present |
| 503 | Not ready / shutting down | |

Error responses never include secrets, stack traces, SQL, or internal paths.

---

## 9. Pagination, Filtering, Idempotency

**Pagination** is cursor-based on every collection:

```text
GET /api/v1/workflows?limit=50&cursor=eyJ…
→ { "items": [...], "next_cursor": "eyJ…" | null }
```

Offset pagination is not used — event and log collections grow during traversal, and offsets would skip or duplicate rows.

**Filtering** uses explicit query parameters only (`status`, `definition_id`, `created_after`, `pack_id`, …). No arbitrary query expressions are accepted from clients.

**Idempotency:** mutating endpoints accept `Idempotency-Key`. Keys are retained 24 hours; a replay returns the original response. A key reused with a different body returns `409`.

**Rate limiting:** per-principal token bucket in Redis. Responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

---

## 10. Relationship with Other Components

- **Workflow Engine** — the API submits and queries; it never orchestrates.
- **Security Manager** — authenticates, builds the `SecurityContext`, authorizes.
- **Evaluation Engine** — supplies experiment and comparison data.
- **Event Bus** — supplies the WebSocket stream.
- **Observability** — every request emits a span; `trace_id` is returned on errors and in the `traceparent` response header.
- **Dashboard, CLI, Voice** — clients with no privileged path ([ADR-0018](../18_decision_log/adr/ADR-0018-dashboard-technology-stack.md), `cli_design.md`, `../14_voice_jarvis/voice_architecture.md`).

---

## 11. Explicitly Not in the API

- **MCP.** Deferred to a future Capability Pack consuming this API; removed from the core API layer ([ADR-0014](../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)).
- **GraphQL.** Rejected; purpose-built endpoints serve the Dashboard.
- **Direct database or vector-store access.** No endpoint exposes raw store access.
- **Prompt or context bodies containing customer source code.** Prompt *identity and version* are exposed; content is not.

---

## 12. Current Status

This document specifies the v1 API surface. Endpoint-level request and response schemas are generated from the FastAPI implementation and published as OpenAPI 3.1; that generated document is the machine-readable contract and is CI-verified against this specification's endpoint list.

---

## 13. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Architecture Decision Records
5. API Architecture (this document)
6. Generated OpenAPI document
7. Source Code
