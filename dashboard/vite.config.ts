/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    css: false,
    // Node's own `fetch` (unlike a real browser) has no page origin to
    // resolve a relative URL against, so `apiClient`'s own real,
    // documented `VITE_API_BASE_URL ?? ""` default needs a real,
    // syntactically valid absolute origin under test — never reached
    // for real, since every test mocks `fetch` itself.
    env: { VITE_API_BASE_URL: "http://localhost:8000" },
  },
});
