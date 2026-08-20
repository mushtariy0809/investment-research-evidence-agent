// Typed client for the backend API. All calls are relative (/api/...) — the
// Vite dev server and the production nginx both proxy them to FastAPI.

export interface Company {
  cik: string;
  ticker: string;
  name: string;
}

export interface Filing {
  id: number;
  accession_number: string;
  form_type: string;
  filing_date: string;
  period_of_report: string | null;
  primary_doc_url: string;
  downloaded: boolean;
  section_count: number;
}

export interface EvidenceItem {
  id: number;
  claim: string;
  excerpt: string;
  section_name: string;
  filing_date: string;
  accession_number: string;
  source_url: string;
  confidence: number;
  status: "proposed" | "verified" | "blocked";
  verdict: string | null;
  citation_valid: boolean | null;
  verification_explanation: string | null;
}

export interface AgentRun {
  agent_name: string;
  status: string;
  input_summary: string;
  output_summary: string;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Brief {
  id: number;
  content_markdown: string;
  version: number;
  created_at: string;
}

export interface ResearchStatus {
  id: number;
  status: string;
  task_type: string;
  question: string;
  filing_id: number;
  compare_filing_id: number | null;
  error: string | null;
  agent_runs: AgentRun[];
  evidence: EvidenceItem[];
  brief: Brief | null;
  missing_info_note: string | null;
}

export interface AuditEvent {
  id: number;
  request_id: number | null;
  actor: string;
  event_type: string;
  payload_json: string;
  prev_hash: string;
  hash: string;
  created_at: string;
}

export interface AuditVerify {
  intact: boolean;
  events_checked: number;
  first_broken_id: number | null;
}

export const TASK_TYPES = [
  { value: "business_overview", label: "Business overview" },
  { value: "risk_factors", label: "Risk factors" },
  { value: "revenue_segments", label: "Revenue / segment disclosures" },
  { value: "management_discussion", label: "Management discussion" },
  { value: "material_changes", label: "Material changes vs. previous filing" },
  { value: "custom", label: "Custom question" },
] as const;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  searchCompanies: (q: string) =>
    request<Company[]>(`/api/companies/search?q=${encodeURIComponent(q)}`),
  listFilings: (company: Company) =>
    request<Filing[]>(
      `/api/companies/${company.cik}/filings?ticker=${encodeURIComponent(
        company.ticker,
      )}&name=${encodeURIComponent(company.name)}`,
    ),
  createResearch: (body: {
    filing_id: number;
    task_type: string;
    question: string;
    compare_filing_id?: number | null;
  }) =>
    request<{ id: number; status: string }>(`/api/research`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getResearch: (id: number) => request<ResearchStatus>(`/api/research/${id}`),
  review: (id: number, decision: string, comment: string) =>
    request<{ status: string; brief_version: number }>(
      `/api/research/${id}/review`,
      { method: "POST", body: JSON.stringify({ decision, comment }) },
    ),
  auditLog: (requestId: number) =>
    request<AuditEvent[]>(`/api/audit?request_id=${requestId}`),
  auditVerify: () => request<AuditVerify>(`/api/audit/verify`),
};
