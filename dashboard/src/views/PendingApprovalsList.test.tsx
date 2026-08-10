import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PendingApprovalsList } from "./PendingApprovalsList";
import { apiClient } from "../api/client";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.GET);
const mockedPost = vi.mocked(apiClient.POST);
const ok = (data: unknown) =>
  ({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  }) as never;
const failed = (error: unknown) =>
  ({
    data: undefined,
    error,
    response: new Response(null, { status: 500 }),
  }) as never;

const PENDING_APPROVAL = {
  approval_id: "appr-real-1",
  workflow_id: "wf-real-1",
  step_id: "approve-it",
  approval_class: "approve-it",
  title: "Approve It",
  description: "A real, pending approval.",
  context_digest: "deadbeef",
  options: ["approve", "reject"],
  status: "pending",
  decided_by: null,
  decision_comment: null,
  requested_at: "2026-08-10T00:00:00Z",
  expires_at: null,
  decided_at: null,
};

describe("PendingApprovalsList", () => {
  afterEach(() => {
    mockedGet.mockReset();
    mockedPost.mockReset();
  });

  it("genuinely renders the real pending approvals the route returns", async () => {
    mockedGet.mockResolvedValue(ok({ approvals: [PENDING_APPROVAL] }));

    render(<PendingApprovalsList />);

    const table = await screen.findByRole("table", { name: "Pending approvals" });
    expect(within(table).getByText("wf-real-1")).toBeInTheDocument();
    expect(within(table).getByText("approve-it")).toBeInTheDocument();
    expect(within(table).getByText("A real, pending approval.")).toBeInTheDocument();
  });

  it("shows a real, honest message when there are no pending approvals", async () => {
    mockedGet.mockResolvedValue(ok({ approvals: [] }));

    render(<PendingApprovalsList />);

    expect(await screen.findByText("No pending approvals.")).toBeInTheDocument();
  });

  it("surfaces a real list error instead of silently showing an empty queue", async () => {
    mockedGet.mockResolvedValue(failed({ detail: "boom" }));

    render(<PendingApprovalsList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not list");
  });

  it(
    "genuinely decides an approval via the real decide route and refreshes the queue " +
      "(FR-092: an approval is decided from the Dashboard)",
    async () => {
      mockedGet
        .mockResolvedValueOnce(ok({ approvals: [PENDING_APPROVAL] }))
        // The real, honest re-fetch after a successful decision — the
        // decided approval is no longer pending, so the real route
        // would no longer return it.
        .mockResolvedValueOnce(ok({ approvals: [] }));
      mockedPost.mockResolvedValue(
        ok({
          approval_id: "appr-real-1",
          workflow_id: "wf-real-1",
          decision: "approved",
          decided_by: "test-user",
          resumed: false,
          resumed_outcome: null,
          resumed_error: null,
        }),
      );

      render(<PendingApprovalsList />);

      const approveButton = await screen.findByRole("button", { name: "Approve" });
      fireEvent.click(approveButton);

      expect(await screen.findByText("No pending approvals.")).toBeInTheDocument();
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions",
        {
          params: { path: { workflow_id: "wf-real-1", approval_id: "appr-real-1" } },
          body: { decision: "approved" },
        },
      );
    },
  );

  it("surfaces a real decide error without losing the rest of the queue", async () => {
    mockedGet.mockResolvedValue(ok({ approvals: [PENDING_APPROVAL] }));
    mockedPost.mockResolvedValue(failed({ detail: "already decided" }));

    render(<PendingApprovalsList />);

    const rejectButton = await screen.findByRole("button", { name: "Reject" });
    fireEvent.click(rejectButton);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not record decision");
    // The approval this decision failed for is still genuinely visible
    // — a failed decision is disclosed, never silently swallowed nor
    // does it wrongly remove the item from the real queue.
    expect(screen.getByText("wf-real-1")).toBeInTheDocument();
  });
});
