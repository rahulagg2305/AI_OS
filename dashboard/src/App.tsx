import { useEffect, useState } from "react";
import { apiClient } from "./api/client";
import "./App.css";

// This ticket's own real, minimal proof of "consuming only the
// generated API client" (ADR-0018) — one real call, through the
// generated, typed client, to a real Kernel endpoint. Richer views
// (TanStack Router/Query, the WebSocket-into-cache pattern, charts)
// are separate, later dashboard tickets — see this pack's own ticket
// for why this shell deliberately stops here.
type VersionInfo = Record<string, string>;

type FetchState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: VersionInfo };

export function App() {
  const [state, setState] = useState<FetchState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function loadVersion() {
      const { data, error } = await apiClient.GET("/api/v1/version");
      if (cancelled) {
        return;
      }
      if (error) {
        setState({ status: "error", message: JSON.stringify(error) });
        return;
      }
      setState({ status: "ready", data });
    }

    void loadVersion();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main>
      <h1>AI_OS Dashboard</h1>
      {state.status === "loading" && <p role="status">Loading version…</p>}
      {state.status === "error" && (
        <p role="alert">Could not reach the Kernel API: {state.message}</p>
      )}
      {state.status === "ready" && (
        <dl aria-label="Kernel version">
          {Object.entries(state.data).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </main>
  );
}

export default App;
