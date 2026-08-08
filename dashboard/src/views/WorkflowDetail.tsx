import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { components } from "../api/schema.gen";

type WorkflowInstance = components["schemas"]["WorkflowInstance"];
type WorkflowStepRecord = components["schemas"]["WorkflowStepRecord"];
type WorkflowEventRecord = components["schemas"]["WorkflowEventRecord"];

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      instance: WorkflowInstance;
      steps: WorkflowStepRecord[];
      events: WorkflowEventRecord[];
    };

export function WorkflowDetail({
  workflowId,
  onBack,
}: {
  workflowId: string;
  onBack: () => void;
}) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    async function load() {
      const [instanceResult, stepsResult, eventsResult] = await Promise.all([
        apiClient.GET("/api/v1/workflows/{workflow_id}", {
          params: { path: { workflow_id: workflowId } },
        }),
        apiClient.GET("/api/v1/workflows/{workflow_id}/steps", {
          params: { path: { workflow_id: workflowId } },
        }),
        apiClient.GET("/api/v1/workflows/{workflow_id}/events", {
          params: { path: { workflow_id: workflowId } },
        }),
      ]);
      if (cancelled) {
        return;
      }
      if (!instanceResult.data) {
        setState({ status: "error", message: JSON.stringify(instanceResult.error) });
        return;
      }
      setState({
        status: "ready",
        instance: instanceResult.data,
        steps: stepsResult.data ?? [],
        events: eventsResult.data ?? [],
      });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  return (
    <section aria-label="Workflow detail">
      <button type="button" onClick={onBack}>
        ← Back to workflows
      </button>
      {state.status === "loading" && <p role="status">Loading workflow {workflowId}…</p>}
      {state.status === "error" && (
        <p role="alert">Could not load workflow {workflowId}: {state.message}</p>
      )}
      {state.status === "ready" && (
        <>
          <h2>{state.instance.workflow_id}</h2>
          <p>
            Status: <strong>{state.instance.status}</strong>
            {state.instance.current_step_id && (
              <> — waiting at step <strong>{state.instance.current_step_id}</strong></>
            )}
          </p>

          <h3>Steps</h3>
          {state.steps.length === 0 ? (
            <p>No steps recorded yet.</p>
          ) : (
            <table aria-label="Steps">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Attempt</th>
                </tr>
              </thead>
              <tbody>
                {state.steps.map((step) => (
                  <tr key={`${step.step_name}-${step.attempt}`}>
                    <td>{step.step_name}</td>
                    <td>{step.step_type}</td>
                    <td>{step.status}</td>
                    <td>{step.attempt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3>Events</h3>
          {state.events.length === 0 ? (
            <p>No events recorded yet.</p>
          ) : (
            <table aria-label="Events">
              <thead>
                <tr>
                  <th>Seq</th>
                  <th>Event type</th>
                  <th>Occurred at</th>
                </tr>
              </thead>
              <tbody>
                {state.events.map((event) => (
                  <tr key={event.event_id}>
                    <td>{event.seq}</td>
                    <td>{event.event_type}</td>
                    <td>{event.occurred_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
