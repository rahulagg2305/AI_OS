import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthView } from "./HealthView";
import { apiClient } from "../api/client";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.GET);

describe("HealthView", () => {
  afterEach(() => {
    mockedGet.mockReset();
  });

  it("renders real liveness and readiness data from the generated client", async () => {
    mockedGet.mockImplementation(async (path) => {
      if (path === "/api/v1/health/live") {
        return {
          data: { status: "live" },
          error: undefined,
          response: new Response(null, { status: 200 }),
        } as Awaited<ReturnType<typeof apiClient.GET>>;
      }
      return {
        data: {
          status: "ready",
          components: [
            { name: "database", status: "ok", detail: "reachable", critical: true },
          ],
        },
        error: undefined,
        response: new Response(null, { status: 200 }),
      } as Awaited<ReturnType<typeof apiClient.GET>>;
    });

    render(<HealthView />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading health");
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("database")).toBeInTheDocument();
    expect(screen.getByText("reachable")).toBeInTheDocument();
  });

  it("shows a real error state when readiness cannot be read", async () => {
    mockedGet.mockResolvedValue({
      data: undefined,
      error: { detail: "database unreachable" },
      response: new Response(null, { status: 503 }),
    } as Awaited<ReturnType<typeof apiClient.GET>>);

    render(<HealthView />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the Kernel API");
  });
});
