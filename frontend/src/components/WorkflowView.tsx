import { useCallback, useEffect, useState } from "react";
import { api, type ResearchStatus } from "../api";
import { AuditLog } from "./AuditLog";
import { BriefView } from "./BriefView";
import { EvidenceTable } from "./EvidenceTable";
import { ProgressPanel } from "./ProgressPanel";
import { ReviewControls } from "./ReviewControls";

type Tab = "progress" | "evidence" | "brief" | "audit";

const ACTIVE_STATES = new Set(["pending", "running"]);

export function WorkflowView({ requestId }: { requestId: number }) {
  const [status, setStatus] = useState<ResearchStatus | null>(null);
  const [tab, setTab] = useState<Tab>("progress");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getResearch(requestId);
      setStatus(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
      return null;
    }
  }, [requestId]);

  // Poll while the pipeline is running; when it finishes, stop polling and
  // move from the progress view to the evidence view exactly once.
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const tick = async () => {
      const data = await refresh();
      if (data && !ACTIVE_STATES.has(data.status)) {
        if (timer) clearInterval(timer);
        timer = undefined;
        setTab((current) => (current === "progress" ? "evidence" : current));
      }
    };
    void tick();
    timer = setInterval(tick, 1500);
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [refresh]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!status) return <p className="muted" aria-live="polite">Loading workflow…</p>;

  const running = ACTIVE_STATES.has(status.status);

  const tabs: { id: Tab; label: string }[] = [
    { id: "progress", label: "Workflow progress" },
    { id: "evidence", label: `Evidence & verification (${status.evidence.length})` },
    { id: "brief", label: "Research brief" },
    { id: "audit", label: "Audit log" },
  ];

  return (
    <section className="card" aria-labelledby="workflow-heading">
      <div className="workflow-header">
        <h2 id="workflow-heading">4. Research workflow #{status.id}</h2>
        <span className={`status status-${status.status}`}>
          {status.status.replaceAll("_", " ")}
        </span>
      </div>
      <p className="muted question-echo">“{status.question}”</p>

      <div role="tablist" className="tabs" aria-label="Workflow views">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "progress" && <ProgressPanel status={status} />}
      {tab === "evidence" && (
        <EvidenceTable
          evidence={status.evidence}
          missingInfoNote={status.missing_info_note}
        />
      )}
      {tab === "brief" && (
        <>
          <BriefView brief={status.brief} running={running} />
          <ReviewControls status={status} onDecision={refresh} />
        </>
      )}
      {tab === "audit" && <AuditLog requestId={status.id} refreshKey={status.status} />}
    </section>
  );
}
