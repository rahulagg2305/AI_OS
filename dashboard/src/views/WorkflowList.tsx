import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { components } from "../api/schema.gen";

type WorkflowInstance = components["schemas"]["WorkflowInstance"];

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: WorkflowInstance[] };

export function WorkflowList({ onSelect }: { onSelect: (workflowId: string) => void }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const { data, error } = await apiClient.GET("/api/v1/workflows");
      if (cancelled) {
        return;
      }
      if (error || !data) {
        setState({ status: "error", message: JSON.stringify(error) });
        return;
      }
      setState({ status: "ready", items: data.items });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p role="status">Loading workflows…</p>;
  }
  if (state.status === "error") {
    return <p role="alert">Could not list workflows: {state.message}</p>;
  }
  if (state.items.length === 0) {
    return <p>No workflow instances found.</p>;
  }

  return (
    <table aria-label="Workflows">
      <thead>
        <tr>
          <th>Workflow ID</th>
          <th>Definition</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {state.items.map((instance) => (
          <tr key={instance.workflow_id}>
            <td>
              <button type="button" onClick={() => onSelect(instance.workflow_id)}>
                {instance.workflow_id}
              </button>
            </td>
            <td>
              {instance.definition_id}@{instance.definition_version}
            </td>
            <td>{instance.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
