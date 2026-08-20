import { useState } from "react";
import type { Company, Filing } from "./api";
import { CompanySearch } from "./components/CompanySearch";
import { FilingPicker } from "./components/FilingPicker";
import { ResearchForm } from "./components/ResearchForm";
import { WorkflowView } from "./components/WorkflowView";

export default function App() {
  const [company, setCompany] = useState<Company | null>(null);
  const [filing, setFiling] = useState<Filing | null>(null);
  const [allFilings, setAllFilings] = useState<Filing[]>([]);
  const [requestId, setRequestId] = useState<number | null>(null);

  function reset() {
    setCompany(null);
    setFiling(null);
    setAllFilings([]);
    setRequestId(null);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Investment Research Evidence Agent</h1>
          <p className="tagline">
            Evidence-backed research briefs from official SEC filings — every claim
            cited, independently verified, and human-approved.
          </p>
        </div>
        {company && (
          <button className="ghost" onClick={reset}>
            Start over
          </button>
        )}
      </header>

      <div className="disclaimer" role="note">
        For research and education only. This tool analyzes public SEC filings and
        does <strong>not</strong> provide investment advice or recommendations.
      </div>

      <main>
        {!company && <CompanySearch onSelect={setCompany} />}
        {company && !filing && (
          <FilingPicker
            company={company}
            onSelect={(selected, all) => {
              setFiling(selected);
              setAllFilings(all);
            }}
          />
        )}
        {company && filing && requestId === null && (
          <ResearchForm
            filing={filing}
            allFilings={allFilings}
            onCreated={setRequestId}
          />
        )}
        {requestId !== null && <WorkflowView requestId={requestId} />}
      </main>

      <footer className="app-footer">
        Data source: SEC EDGAR (official). LLM output is verified against filing
        text before it can appear in a brief.
      </footer>
    </div>
  );
}
