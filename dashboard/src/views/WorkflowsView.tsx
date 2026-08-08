import { useState } from "react";
import { WorkflowList } from "./WorkflowList";
import { WorkflowDetail } from "./WorkflowDetail";

// The real drill-down this ticket's own Output requires: a list view
// and a detail view, switched by plain component state — no router
// dependency yet (deliberately deferred, matching
// `P06-S03-M39-T01`'s own "smallest real slice" precedent; TanStack
// Router is separate, later work).
export function WorkflowsView() {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);

  if (selectedWorkflowId) {
    return (
      <WorkflowDetail
        workflowId={selectedWorkflowId}
        onBack={() => setSelectedWorkflowId(null)}
      />
    );
  }

  return <WorkflowList onSelect={setSelectedWorkflowId} />;
}
