import { useEffect, useState } from "react";
import { api, type Company, type Filing } from "../api";

export function FilingPicker({
  company,
  onSelect,
}: {
  company: Company;
  onSelect: (filing: Filing, all: Filing[]) => void;
}) {
  const [filings, setFilings] = useState<Filing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listFilings(company)
      .then((data) => {
        if (!cancelled) setFilings(data);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load filings");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [company]);

  return (
    <section className="card" aria-labelledby="filings-heading">
      <h2 id="filings-heading">
        2. Choose a filing — {company.name} ({company.ticker})
      </h2>
      {loading && <p className="muted" aria-live="polite">Loading filings from SEC EDGAR…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && filings.length === 0 && (
        <p className="muted">No 10-K or 10-Q filings found for this company.</p>
      )}
      {filings.length > 0 && (
        <table>
          <thead>
            <tr>
              <th scope="col">Form</th>
              <th scope="col">Filed</th>
              <th scope="col">Period</th>
              <th scope="col">Accession no.</th>
              <th scope="col" className="visually-hidden">Action</th>
            </tr>
          </thead>
          <tbody>
            {filings.map((filing) => (
              <tr key={filing.id}>
                <td>
                  <span className={`badge form-${filing.form_type.toLowerCase()}`}>
                    {filing.form_type}
                  </span>
                </td>
                <td>{filing.filing_date}</td>
                <td>{filing.period_of_report ?? "—"}</td>
                <td className="mono">
                  <a href={filing.primary_doc_url} target="_blank" rel="noreferrer">
                    {filing.accession_number}
                  </a>
                </td>
                <td>
                  <button onClick={() => onSelect(filing, filings)}>Research</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
