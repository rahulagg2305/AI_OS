// A real, minimal stand-in for ADR-0014's own documented auth model
// ("OIDC bearer tokens for humans") — no OIDC login flow exists in this
// dashboard yet (deliberately deferred, matching `P06-S03-M39-T01`'s
// own "smallest real slice" precedent). This is not a parallel auth
// mechanism: it stores exactly the same Bearer token the real Kernel
// already expects on every `Authorization` header, just without a
// redirect-based login UI in front of it. A real future login flow
// replaces `getToken`/`setToken`'s own storage, not the header contract
// `client.ts`'s middleware already establishes.
const STORAGE_KEY = "aios.dashboard.token";

export function getToken(): string | null {
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    window.localStorage.setItem(STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}
