import { useState } from "react";
import { api, TASK_TYPES, type Filing } from "../api";

const SUGGESTED_QUESTIONS: Record<string, string> = {
  business_overview:
    "What products and services does the company sell, and through which segments?",
  risk_factors: "What are the most significant risk factors disclosed?",
  revenue_segments: "How did revenue change and which segments drove the change?",
  management_discussion:
    "What does management highlight about results of operations and trends?",
  material_changes:
    "What material changes in risks or strategy occurred since the previous filing?",
  custom: "",
};

export function ResearchForm({
  filing,
  allFilings,
  onCreated,
}: {
  filing: Filing;
  allFilings: Filing[];
  onCreated: (requestId: number) => void;
}) {
  const [taskType, setTaskType] = useState<string>("risk_factors");
  const [question, setQuestion] = useState(SUGGESTED_QUESTIONS.risk_factors);
  const [compareId, setCompareId] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const compareOptions = allFilings.filter((f) => f.id !== filing.id);
  const needsCompare = taskType === "material_changes";

  function changeTask(value: string) {
    setTaskType(value);
    setQuestion(SUGGESTED_QUESTIONS[value] ?? "");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createResearch({
        filing_id: filing.id,
        task_type: taskType,
        question: question.trim(),
        compare_filing_id: compareId === "" ? null : compareId,
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start research");
      setSubmitting(false);
    }
  }

  return (
    <section className="card" aria-labelledby="question-heading">
      <h2 id="question-heading">
        3. Ask a research question — {filing.form_type} filed {filing.filing_date}
      </h2>
      <form onSubmit={submit} className="stack">
        <div className="field">
          <label htmlFor="task-select">Research task</label>
          <select
            id="task-select"
            value={taskType}
            onChange={(e) => changeTask(e.target.value)}
          >
            {TASK_TYPES.map((task) => (
              <option key={task.value} value={task.value}>
                {task.label}
              </option>
            ))}
          </select>
        </div>

        {(needsCompare || compareId !== "") && (
          <div className="field">
            <label htmlFor="compare-select">
              Compare against {needsCompare ? "(required)" : "(optional)"}
            </label>
            <select
              id="compare-select"
              value={compareId}
              onChange={(e) =>
                setCompareId(e.target.value === "" ? "" : Number(e.target.value))
              }
              required={needsCompare}
            >
              <option value="">— select a previous filing —</option>
              {compareOptions.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.form_type} filed {f.filing_date}
                </option>
              ))}
            </select>
          </div>
        )}
        {needsCompare && compareOptions.length === 0 && (
          <p className="error">No other filing available to compare against.</p>
        )}

        <div className="field">
          <label htmlFor="question-input">Question (5–500 characters)</label>
          <textarea
            id="question-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            minLength={5}
            maxLength={500}
            required
          />
        </div>

        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={submitting || (needsCompare && compareId === "")}>
          {submitting ? "Starting research…" : "Run evidence-backed research"}
        </button>
      </form>
    </section>
  );
}
