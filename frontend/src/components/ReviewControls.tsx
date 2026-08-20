import { useState } from "react";
import { api, type ResearchStatus } from "../api";

export function ReviewControls({
  status,
  onDecision,
}: {
  status: ResearchStatus;
  onDecision: () => void;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status.status !== "awaiting_review") {
    if (["approved", "rejected"].includes(status.status)) {
      return (
        <p className="notice">
          Final decision recorded: <strong>{status.status}</strong>. The audit log
          keeps the full history.
        </p>
      );
    }
    return null;
  }

  async function decide(decision: string) {
    if (decision === "revision_requested" && comment.trim() === "") {
      setError("Please describe the revision you want.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.review(status.id, decision, comment.trim());
      setComment("");
      onDecision();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-panel">
      <h3>Human review</h3>
      <p className="muted small">
        Nothing is final until a person signs off. Approve the brief, reject it,
        or request a revision (the brief is rewritten from the same verified
        evidence).
      </p>
      <label htmlFor="review-comment">Comment (required for revisions)</label>
      <textarea
        id="review-comment"
        rows={2}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        maxLength={2000}
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button className="approve" disabled={busy} onClick={() => decide("approved")}>
          Approve
        </button>
        <button className="revise" disabled={busy} onClick={() => decide("revision_requested")}>
          Request revision
        </button>
        <button className="reject" disabled={busy} onClick={() => decide("rejected")}>
          Reject
        </button>
      </div>
    </div>
  );
}
