import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { apiClient } from "./api/client";

// `openapi-fetch`'s own `createClient` captures `globalThis.fetch` once,
// as a default-parameter value, at client-construction time (its own
// source: `fetch: baseFetch = globalThis.fetch`) — since `apiClient` is
// a module-level singleton built before any test runs, stubbing
// `globalThis.fetch` later never reaches it. Mocking `./api/client`'s
// own `GET` method directly is the real seam this component actually
// depends on, and the standard way to test a component built on a
// fixed API client — not a workaround for the library's behaviour.
vi.mock("./api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.GET);

describe("App", () => {
  afterEach(() => {
    mockedGet.mockReset();
  });

  it("renders the real version payload returned by the generated API client", async () => {
    mockedGet.mockResolvedValue({
      data: {
        service: "ai-os-kernel",
        version: "0.1.0",
        environment: "test",
        role: "api",
      },
      error: undefined,
      response: new Response(),
    } as Awaited<ReturnType<typeof apiClient.GET>>);

    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading version");

    const version = await screen.findByText("0.1.0");
    expect(version).toBeInTheDocument();
    expect(screen.getByText("ai-os-kernel")).toBeInTheDocument();
    expect(mockedGet).toHaveBeenCalledWith("/api/v1/version");
  });

  it("shows a real error state when the Kernel API call fails", async () => {
    mockedGet.mockResolvedValue({
      data: undefined,
      error: { detail: "service unavailable" },
      response: new Response(),
    } as Awaited<ReturnType<typeof apiClient.GET>>);

    render(<App />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the Kernel API");
  });
});
