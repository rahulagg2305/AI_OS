import { PendingApprovalsList } from "./PendingApprovalsList";

// No drill-down/detail view yet, unlike WorkflowsView — every field
// FR-092 requires (decision context, a real accept/reject action) is
// already real in the list itself (api_architecture.md §6.2 documents
// a separate `GET /approvals/{id}` detail route too, still genuinely
// not built — see this pack's own Implementation Status). A thin
// wrapper component, matching this dashboard's own established
// one-view-per-tab shape, so a future detail view can be added here
// without changing `App.tsx`.
export function PendingApprovalsView() {
  return <PendingApprovalsList />;
}
