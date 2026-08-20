# Interview notes

Working answers for the questions this project will attract. Everything here
is true of the code — verify any claim by reading the referenced file.

## Why I built this

I'm targeting software engineering / AI roles in financial services, where the
hard problem with LLMs isn't capability, it's **trust**: hallucinated numbers
and invented citations are disqualifying in a regulated environment. I built a
system whose architecture makes untrustworthy output structurally difficult:
grounding, independent verification, human sign-off, and an audit trail. The
domain (SEC filings) is real, public, and free, so the data pipeline is real
too — official EDGAR APIs, not scraped or synthetic data.

## Why multiple agents instead of one prompt

One prompt gives one blob of text you can only trust or distrust as a whole.
Splitting the pipeline gives:

1. **Checkable seams.** Extraction output is a typed list of claim+excerpt
   objects — small enough to verify individually.
2. **Independence.** The verifier never sees why extraction chose a claim; it
   only judges claim vs. source. That's the same reason code review isn't done
   by the author.
3. **Least privilege.** The one component with network access (SEC retrieval)
   has no LLM; the components with LLMs have no tools. An injected instruction
   in a filing has nothing to invoke.
4. **Testability.** Each agent is a class taking Pydantic models; I can unit
   test the verifier with a hostile fake provider that returns garbage.

I did *not* use an agent framework: five agents with typed hand-offs is ~600
lines of plain Python, and I can explain every line. A framework would add a
dependency and hide exactly the control flow this project exists to showcase.

## How verification reduces hallucinations

Two layers, in order:

1. **Deterministic citation check (code, not model):** the quoted excerpt must
   appear verbatim (whitespace/quote-normalized) in the section it cites. A
   fabricated quote fails here with probability 1 — this layer cannot be
   sweet-talked. (`textutil.excerpt_appears_in`)
2. **Semantic check (LLM):** given claim + excerpt + full section, classify
   supported / partially / unsupported / contradicted. Unknown verdicts fail
   closed.

Claims failing either layer are `blocked`, never reach the brief writer, and
the brief writer independently re-checks verdicts and refuses non-passing
evidence. The eval plants a fabricated citation and CI fails unless it's
blocked. Also key: the model never *generates* citation metadata — accession
numbers, dates, and URLs are attached by code from the database, so they can't
be hallucinated in the first place.

## How citations are preserved end to end

Filing → sections stored with names → extraction returns (claim, excerpt,
section_name, filing_label) → code resolves filing_label to trusted metadata →
Evidence row stores the full citation denormalized → verification re-reads the
section text by accession+name from the DB → brief writer receives evidence
with `[E#]` refs and must cite them inline → UI renders excerpt, section,
accession number (linked to the SEC document), and filing date per claim.

## Prompt injection handling

Filing text is untrusted input, full stop. Four layers (docs/responsible-ai.md
has the detail): delimiter-wrapping with bracket neutralization so the payload
can't fake a closing tag; a pattern scanner whose findings become audit
events a reviewer sees; containment — the agents that read filings have no
tools and can only emit JSON validated by Pydantic; and the verification
backstop — even manipulated extraction can only propose claims, which still
have to survive the verbatim citation check, and advice language in a brief
causes the brief to be rejected. I treat the scanner as a tripwire, not a
guarantee; containment and verification are the load-bearing layers.

## Database and API design

- SQLAlchemy 2.0 typed ORM, ten tables (Company, Filing, FilingSection,
  ResearchRequest, AgentRun, Evidence, ClaimVerification, ResearchBrief,
  HumanReview, AuditEvent). SQLite locally; nothing SQLite-specific is used, so
  PostgreSQL is literally a `DATABASE_URL` change.
- Evidence denormalizes its citation so a row is self-contained; briefs are
  versioned inserts (never updates) for the audit story; audit events are
  append-only with a SHA-256 hash chain, and an endpoint re-verifies the chain.
- REST API: `202 + poll` for the long-running pipeline (BackgroundTasks +
  status polling), `409` for review-state conflicts, `502` for upstream SEC
  failures, `422` with clear messages for validation. Pydantic models define
  every request/response; FastAPI generates the OpenAPI docs.

## Testing decisions

- 42 pytest tests: unit tests for the parser, relevance ranking, injection
  guard, audit chain (including a tampering test), each agent (including
  hostile fake providers returning garbage verdicts, advice language, and
  hallucinated filing labels), plus API-level integration tests that run the
  whole workflow over HTTP.
- No network in tests: a `FakeSecClient` serves a synthetic fixture filing;
  the mock LLM makes everything deterministic. TestClient runs background
  tasks synchronously, so the full pipeline is exercised in-process.
- The mock provider is grounded (quotes real fixture sentences), so tests
  exercise the actual safety mechanisms rather than mocking them away.
- Separately, an evaluation harness measures quality (citation validity,
  support rate, retrieval recall, verification agreement, latency) with CI
  thresholds — tests prove correctness, the eval measures behavior.

## Technical tradeoffs I can defend

- **Keyword retrieval over embeddings:** transparent, deterministic, free, and
  measurable; the eval showed recall 1.0 on the fixture set at precision 0.53.
  Embeddings are the next step and slot behind the same `rank_sections`
  function with the same metric.
- **Heuristic section parser over a parsing library:** SEC HTML is chaotic;
  my parser is ~150 auditable lines with a chunking fallback, and downstream
  verification doesn't depend on perfect sectioning.
- **BackgroundTasks over a task queue:** right-sized for a single-user MVP;
  the orchestrator already opens its own DB session, so moving it onto a
  worker queue doesn't change its code.
- **Naive-UTC timestamps:** SQLite drops timezones; a tz-aware datetime would
  re-serialize differently and falsely break the audit hash chain. I hit this
  bug, diagnosed it, and documented the fix in the model layer.
- **Mock-first design:** the provider interface forced clean seams and makes
  the repo runnable by anyone (including CI) with zero credentials.

## What I would improve for production

Postgres + Alembic migrations; a real task queue with retries and idempotency
keys; embedding retrieval with reranking; XBRL cross-checks for numeric
claims; authentication/authorization and per-user audit attribution; rate
limiting; observability (metrics + tracing on each agent step); a second
independent verifier model to measure inter-verifier agreement; and periodic
live-EDGAR integration tests separated from the unit suite.

## Résumé bullet templates (fill metrics only after measuring)

> Built an AI research platform (Python/FastAPI, React/TypeScript, Anthropic
> API) that generates evidence-cited briefs from SEC filings using a
> five-agent pipeline with independent claim verification; achieved __%
> citation validity and blocked __% of planted unsupported claims on a
> __-question evaluation set.

> Designed responsible-AI safeguards for a financial document-analysis tool —
> verbatim citation checking, generation/verification separation, hash-chained
> audit logging, and prompt-injection containment — validated by __ automated
> tests and a CI-gated evaluation harness running entirely offline via a
> deterministic mock-LLM provider.

(For the first bullet, mock-mode numbers are 100% / 100% on 12 questions +
4 probes, but measure with `LLM_PROVIDER=anthropic` before quoting numbers as
model performance.)
