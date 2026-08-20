import type { ResearchStatus } from "../api";

const PIPELINE = [
  { key: "evidence_extraction", label: "Evidence extraction" },
  { key: "verification", label: "Claim verification" },
  { key: "brief_writer", label: "Brief writing" },
];

export function ProgressPanel({ status }: { status: ResearchStatus }) {
  const runsByAgent = new Map(status.agent_runs.map((run) => [run.agent_name, run]));

  return (
    <div aria-live="polite">
      <ol className="pipeline">
        {PIPELINE.map((step) => {
          const run = runsByAgent.get(step.key);
          const state = run ? run.status : "waiting";
          return (
            <li key={step.key} className={`pipeline-step ${state}`}>
              <span className="step-state">
                {state === "succeeded" ? "✓" : state === "failed" ? "✗" : state === "running" ? "…" : "•"}
              </span>
              <div>
                <strong>{step.label}</strong>
                <div className="muted small">
                  {run ? run.output_summary || run.input_summary : "Waiting"}
                  {run?.error && <span className="error"> — {run.error}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {status.status === "failed" && (
        <p className="error" role="alert">
          Research failed: {status.error ?? "unknown error"}
        </p>
      )}
      {status.missing_info_note && (
        <p className="notice">
          <strong>Extraction note:</strong> {status.missing_info_note}
        </p>
      )}
    </div>
  );
}
