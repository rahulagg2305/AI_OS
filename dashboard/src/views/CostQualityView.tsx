import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { components } from "../api/schema.gen";

type CostAndQualityReport = components["schemas"]["CostAndQualityReport"];
type CostBreakdownEntry = components["schemas"]["CostBreakdownEntry"];

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; report: CostAndQualityReport };

function BreakdownTable({
  caption,
  entries,
}: {
  caption: string;
  entries: CostBreakdownEntry[];
}) {
  return (
    <table>
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th>Dimension</th>
          <th>Calls</th>
          <th>Input tokens</th>
          <th>Output tokens</th>
          <th>Cost (USD)</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <tr key={entry.dimension_value}>
            <td>{entry.dimension_value}</td>
            <td>{entry.call_count}</td>
            <td>{entry.total_input_tokens}</td>
            <td>{entry.total_output_tokens}</td>
            <td>{entry.total_cost_usd}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function CostQualityView() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const result = await apiClient.GET("/api/v1/evaluation/cost-and-quality");
      if (cancelled) {
        return;
      }
      if (!result.data) {
        setState({ status: "error", message: JSON.stringify(result.error) });
        return;
      }
      setState({ status: "ready", report: result.data });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p role="status">Loading cost and quality report…</p>;
  }
  if (state.status === "error") {
    return <p role="alert">Could not reach the Kernel API: {state.message}</p>;
  }

  const { report } = state;

  return (
    <section aria-label="Cost and Quality">
      <BreakdownTable caption="Cost by model" entries={report.by_model} />
      <BreakdownTable caption="Cost by workflow" entries={report.by_workflow} />
      <BreakdownTable caption="Cost by agent" entries={report.by_agent} />
      <BreakdownTable caption="Cost by pack" entries={report.by_pack} />
      <table>
        <caption>Gate failures (most frequent first)</caption>
        <thead>
          <tr>
            <th>Gate</th>
            <th>Status</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {report.gate_failures.map((entry) => (
            <tr key={`${entry.gate_id}:${entry.status}`}>
              <td>{entry.gate_id}</td>
              <td>{entry.status}</td>
              <td>{entry.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
