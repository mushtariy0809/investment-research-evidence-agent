import { useState } from "react";
import { api, type Company } from "../api";

export function CompanySearch({
  onSelect,
}: {
  onSelect: (company: Company) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Company[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResults(await api.searchCompanies(query.trim()));
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card" aria-labelledby="search-heading">
      <h2 id="search-heading">1. Find a company</h2>
      <form onSubmit={search} className="row">
        <label className="visually-hidden" htmlFor="ticker-input">
          Company ticker or name
        </label>
        <input
          id="ticker-input"
          type="text"
          placeholder="Ticker or company name (e.g. AAPL)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {searched && results.length === 0 && !error && (
        <p className="muted">No companies matched “{query}”.</p>
      )}
      {results.length > 0 && (
        <table>
          <thead>
            <tr>
              <th scope="col">Ticker</th>
              <th scope="col">Company</th>
              <th scope="col">CIK</th>
              <th scope="col" className="visually-hidden">Action</th>
            </tr>
          </thead>
          <tbody>
            {results.map((company) => (
              <tr key={company.cik + company.ticker}>
                <td className="mono">{company.ticker}</td>
                <td>{company.name}</td>
                <td className="mono">{company.cik}</td>
                <td>
                  <button onClick={() => onSelect(company)}>Select</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
