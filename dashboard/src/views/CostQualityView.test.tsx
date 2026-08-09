import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CostQualityView } from "./CostQualityView";
import { apiClient } from "../api/client";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.GET);

describe("CostQualityView", () => {
  afterEach(() => {
    mockedGet.mockReset();
  });

  it("renders real cost breakdowns and gate failures from the generated client", async () => {
    mockedGet.mockResolvedValue({
      data: {
        by_model: [
          {
            dimension_value: "claude-opus-5",
            call_count: 2,
            total_input_tokens: 300,
            total_output_tokens: 150,
            total_cost_usd: "4.000000",
          },
        ],
        by_workflow: [],
        by_agent: [],
        by_pack: [],
        gate_failures: [
          { gate_id: "quality-gate-lint-clean", status: "failed", count: 2 },
        ],
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    } as Awaited<ReturnType<typeof apiClient.GET>>);

    render(<CostQualityView />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading cost and quality report");
    expect(await screen.findByText("claude-opus-5")).toBeInTheDocument();
    expect(screen.getByText("4.000000")).toBeInTheDocument();
    expect(screen.getByText("quality-gate-lint-clean")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows a real error state when the report cannot be read", async () => {
    mockedGet.mockResolvedValue({
      data: undefined,
      error: { detail: "evaluation reporting is not available" },
      response: new Response(null, { status: 503 }),
    } as Awaited<ReturnType<typeof apiClient.GET>>);

    render(<CostQualityView />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the Kernel API");
  });
});
