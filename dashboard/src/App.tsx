import { useState } from "react";
import { TokenBar } from "./auth/TokenBar";
import { HealthView } from "./views/HealthView";
import { WorkflowsView } from "./views/WorkflowsView";
import { CostQualityView } from "./views/CostQualityView";
import { PendingApprovalsView } from "./views/PendingApprovalsView";
import "./App.css";

type Tab = "health" | "workflows" | "cost-quality" | "approvals";

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
        <button
          type="button"
          aria-pressed={tab === "cost-quality"}
          onClick={() => setTab("cost-quality")}
        >
          Cost & Quality
        </button>
        <button
          type="button"
          aria-pressed={tab === "approvals"}
          onClick={() => setTab("approvals")}
        >
          Approvals
        </button>
      </nav>
      {tab === "health" ? (
        <HealthView />
      ) : tab === "workflows" ? (
        <WorkflowsView />
      ) : tab === "cost-quality" ? (
        <CostQualityView />
      ) : (
        <PendingApprovalsView />
      )}
    </main>
  );
}

export default App;
