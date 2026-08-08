# AI_OS Dashboard

The Dashboard's real, minimal shell — `P06-S02-M39-T01`, ADR-0018,
scoped narrowly to this ticket's own Goal: "Stand up React/TS/Vite
consuming only the generated API client." React 19, TypeScript
(`strict: true`), Vite. Nothing else from ADR-0018's own fuller target
stack (TanStack Router/Query, the WebSocket-into-cache pattern,
Tailwind, shadcn/ui, Recharts, Playwright e2e) is built yet — those are
separate, later dashboard tickets.

## The generated API client

`src/api/schema.gen.ts` is generated from the real, published
`docs/07_api/openapi.json` — never hand-edited (ADR-0018: "Hand-written
API client — Rejected: guarantees drift from the OpenAPI contract.").

```sh
npm run generate:api-client   # regenerate after the OpenAPI contract changes
npm run check:api-client      # fails if the committed file has drifted (CI runs this)
```

`src/api/client.ts` wraps it with `openapi-fetch`, a real, fully-typed
fetch client. `VITE_API_BASE_URL` (see `.env.example`) controls where
it sends requests; unset resolves to same-origin relative requests.

## Development

```sh
npm ci
npm run dev            # http://localhost:5173
npm run build           # tsc -b && vite build — the real production build
npm run test -- --run   # vitest, one-shot
npm run lint             # oxlint
```
