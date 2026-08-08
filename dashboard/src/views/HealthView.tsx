import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { components } from "../api/schema.gen";

type ReadinessReport = components["schemas"]["ReadinessReport"];

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; live: boolean; readiness: ReadinessReport };

export function HealthView() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [liveResult, readyResult] = await Promise.all([
        apiClient.GET("/api/v1/health/live"),
        apiClient.GET("/api/v1/health/ready"),
      ]);
      if (cancelled) {
        return;
      }
      if (!readyResult.data) {
        setState({ status: "error", message: JSON.stringify(readyResult.error) });
        return;
      }
      setState({
        status: "ready",
        live: liveResult.response.ok,
        readiness: readyResult.data,
      });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p role="status">Loading health…</p>;
  }
  if (state.status === "error") {
    return <p role="alert">Could not reach the Kernel API: {state.message}</p>;
  }

  return (
    <section aria-label="Health">
      <p>
        Liveness: <strong>{state.live ? "live" : "unreachable"}</strong>
      </p>
      <p>
        Readiness: <strong>{state.readiness.status}</strong>
      </p>
      <table>
        <thead>
          <tr>
            <th>Component</th>
            <th>Status</th>
            <th>Critical</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {state.readiness.components.map((component) => (
            <tr key={component.name}>
              <td>{component.name}</td>
              <td>{component.status}</td>
              <td>{component.critical ? "yes" : "no"}</td>
              <td>{component.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
