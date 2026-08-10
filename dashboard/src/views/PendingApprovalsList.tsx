import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { components } from "../api/schema.gen";

type Approval = components["schemas"]["Approval"];

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: Approval[] };

// FR-092's own acceptance criterion ("An approval is decided from the
// Dashboard and the workflow resumes") is why this list carries a real
// decide action inline, not just a read-only render — the first real
// mutation this dashboard shell makes, reusing the already-real
// `POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions`
// route unchanged (`P03-S03-M30-T06`), never a second decide mechanism.
export function PendingApprovalsList() {
  const [state, setState] = useState<State>({ status: "loading" });
  // Per-approval in-flight/error tracking, keyed by approval_id — one
  // decision failing must never block or hide the rest of the queue.
  const [decidingIds, setDecidingIds] = useState<Set<string>>(new Set());
  const [decisionErrors, setDecisionErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setState({ status: "loading" });
    const { data, error } = await apiClient.GET("/api/v1/approvals");
    if (error || !data) {
      setState({ status: "error", message: JSON.stringify(error) });
      return;
    }
    setState({ status: "ready", items: data.approvals });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(approval: Approval, decision: "approved" | "rejected") {
    setDecidingIds((prev) => new Set(prev).add(approval.approval_id));
    setDecisionErrors((prev) => {
      const next = { ...prev };
      delete next[approval.approval_id];
      return next;
    });

    const { data, error } = await apiClient.POST(
      "/api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions",
      {
        params: {
          path: { workflow_id: approval.workflow_id, approval_id: approval.approval_id },
        },
        body: { decision },
      },
    );

    setDecidingIds((prev) => {
      const next = new Set(prev);
      next.delete(approval.approval_id);
      return next;
    });

    if (error || !data) {
      setDecisionErrors((prev) => ({
        ...prev,
        [approval.approval_id]: JSON.stringify(error),
      }));
      return;
    }

    // The real, decided approval no longer belongs in the *pending*
    // queue — re-fetching from the real route is the honest source of
    // truth (never assumed locally), the identical "never trust the
    // response body alone" discipline this codebase's own backend
    // tests already establish.
    await load();
  }

  if (state.status === "loading") {
    return <p role="status">Loading pending approvals…</p>;
  }
  if (state.status === "error") {
    return <p role="alert">Could not list pending approvals: {state.message}</p>;
  }
  if (state.items.length === 0) {
    return <p>No pending approvals.</p>;
  }

  return (
    <table aria-label="Pending approvals">
      <thead>
        <tr>
          <th>Workflow</th>
          <th>Approval class</th>
          <th>Description</th>
          <th>Requested at</th>
          <th>Decision</th>
        </tr>
      </thead>
      <tbody>
        {state.items.map((approval) => {
          const isDeciding = decidingIds.has(approval.approval_id);
          const decisionError = decisionErrors[approval.approval_id];
          return (
            <tr key={approval.approval_id}>
              <td>{approval.workflow_id}</td>
              <td>{approval.approval_class}</td>
              <td>{approval.description}</td>
              <td>{approval.requested_at}</td>
              <td>
                <button
                  type="button"
                  disabled={isDeciding}
                  onClick={() => void decide(approval, "approved")}
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={isDeciding}
                  onClick={() => void decide(approval, "rejected")}
                >
                  Reject
                </button>
                {decisionError && (
                  <p role="alert">Could not record decision: {decisionError}</p>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
