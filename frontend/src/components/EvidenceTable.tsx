import type { EvidenceItem } from "../api";

function VerdictBadge({ item }: { item: EvidenceItem }) {
  if (!item.verdict) return <span className="badge">pending</span>;
  const cls = item.status === "verified" ? "badge ok" : "badge blocked";
  return (
    <span className={cls}>
      {item.verdict.replaceAll("_", " ")}
      {item.citation_valid === false && " (invalid citation)"}
    </span>
  );
}

export function EvidenceTable({
  evidence,
  missingInfoNote,
}: {
  evidence: EvidenceItem[];
  missingInfoNote: string | null;
}) {
  if (evidence.length === 0) {
    return (
      <p className="muted">
        No evidence extracted.{" "}
        {missingInfoNote ?? "The pipeline may still be running."}
      </p>
    );
  }
  return (
    <div className="table-scroll">
      <table className="evidence-table">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Claim</th>
            <th scope="col">Supporting excerpt</th>
            <th scope="col">Source</th>
            <th scope="col">Confidence</th>
            <th scope="col">Verification</th>
          </tr>
        </thead>
        <tbody>
          {evidence.map((item, index) => (
            <tr key={item.id} className={item.status === "blocked" ? "row-blocked" : ""}>
              <td className="mono">E{index + 1}</td>
              <td>{item.claim}</td>
              <td>
                <blockquote className="excerpt">“{item.excerpt}”</blockquote>
              </td>
              <td className="small">
                {item.section_name}
                <br />
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  {item.accession_number}
                </a>
                <br />
                filed {item.filing_date}
              </td>
              <td className="mono">{item.confidence.toFixed(2)}</td>
              <td>
                <VerdictBadge item={item} />
                {item.verification_explanation && (
                  <div className="small muted">{item.verification_explanation}</div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
