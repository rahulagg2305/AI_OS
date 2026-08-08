import { useState } from "react";
import { TokenBar } from "./auth/TokenBar";
import { HealthView } from "./views/HealthView";
import { WorkflowsView } from "./views/WorkflowsView";
import "./App.css";

type Tab = "health" | "workflows";

export function App() {
  const [tab, setTab] = useState<Tab>("health");

  return (
    <main>
      <h1>AI_OS Dashboard</h1>
      <TokenBar />
      <nav aria-label="Views">
        <button
          type="button"
          aria-pressed={tab === "health"}
          onClick={() => setTab("health")}
        >
          Health
        </button>
        <button
          type="button"
          aria-pressed={tab === "workflows"}
          onClick={() => setTab("workflows")}
        >
          Workflows
        </button>
      </nav>
      {tab === "health" ? <HealthView /> : <WorkflowsView />}
    </main>
  );
}

export default App;
