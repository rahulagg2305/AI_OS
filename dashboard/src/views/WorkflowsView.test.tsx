import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkflowsView } from "./WorkflowsView";
import { apiClient } from "../api/client";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.GET);
const ok = (data: unknown) =>
  ({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  }) as Awaited<ReturnType<typeof apiClient.GET>>;

describe("WorkflowsView", () => {
  afterEach(() => {
    mockedGet.mockReset();
  });

  it("genuinely drills down from the list into a real workflow's own detail", async () => {
    mockedGet.mockImplementation(async (path) => {
      if (path === "/api/v1/workflows") {
        return ok({
          items: [
            {
              workflow_id: "wf-real-1",
              definition_id: "se.delivery_pipeline",
              definition_version: "1.9.0",
              status: "running",
              current_step_id: "build",
              created_at: "2026-08-08T00:00:00Z",
              updated_at: "2026-08-08T00:00:00Z",
              completed_at: null,
              inputs: {},
              outputs: null,
              error: null,
              experiment_id: null,
              run_manifest_id: null,
              principal_id: "test-user",
              principal_permissions: null,
              scheduled_at: null,
              last_event_seq: 1,
              total_cost_usd: "0",
              total_tokens: 0,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/v1/workflows/{workflow_id}") {
        return ok({
          workflow_id: "wf-real-1",
          definition_id: "se.delivery_pipeline",
          definition_version: "1.9.0",
          status: "running",
          current_step_id: "build",
          created_at: "2026-08-08T00:00:00Z",
          updated_at: "2026-08-08T00:00:00Z",
          completed_at: null,
          inputs: {},
          outputs: null,
          error: null,
          experiment_id: null,
          run_manifest_id: null,
          principal_id: "test-user",
          principal_permissions: null,
          scheduled_at: null,
          last_event_seq: 1,
          total_cost_usd: "0",
          total_tokens: 0,
        });
      }
      if (path === "/api/v1/workflows/{workflow_id}/steps") {
        return ok([
          {
            step_id: "step-1",
            step_name: "build",
            step_type: "agent",
            status: "running",
            attempt: 1,
            agent_id: "software-engineering/build",
            model_alias: null,
            prompt_id: null,
            prompt_version: null,
            tool_id: null,
            inputs: {},
            outputs: null,
            error: null,
            idempotency_key: "idem-1",
            started_at: "2026-08-08T00:00:00Z",
            completed_at: null,
          },
        ]);
      }
      return ok([]);
    });

    render(<WorkflowsView />);

    const workflowButton = await screen.findByRole("button", { name: "wf-real-1" });
    fireEvent.click(workflowButton);

    expect(await screen.findByRole("heading", { name: "wf-real-1" })).toBeInTheDocument();
    const stepsTable = screen.getByRole("table", { name: "Steps" });
    expect(within(stepsTable).getByText("build")).toBeInTheDocument();
    expect(within(stepsTable).getByText("agent")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /back to workflows/i }));
    expect(await screen.findByRole("button", { name: "wf-real-1" })).toBeInTheDocument();
  });
});
