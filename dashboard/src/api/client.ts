// The one real, generated-typed API client this dashboard shell may
// use (ADR-0018: "Hand-written API client — Rejected: guarantees drift
// from the OpenAPI contract."). `paths` is generated from the real,
// published `docs/07_api/openapi.json` (`npm run generate:api-client`)
// — never hand-edited (see schema.gen.ts's own header).
import createClient from "openapi-fetch";
import type { paths } from "./schema.gen";

// No hardcoded base URL: `VITE_API_BASE_URL` is a real, documented Vite
// env var (`.env`/deployment config), defaulting to a same-origin
// relative path so the dashboard works out of the box when served
// behind the same API gateway ADR-0018 §"Neutral" describes.
const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

export const apiClient = createClient<paths>({ baseUrl });
