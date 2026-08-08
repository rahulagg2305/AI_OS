import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// `@testing-library/react`'s own auto-cleanup only registers itself
// against a *global* `afterEach` (i.e. `test.globals: true` in Vite
// config) — this project's own tests import `afterEach` explicitly
// from `vitest` instead, so cleanup is wired here, once, explicitly.
afterEach(() => {
  cleanup();
});
