#!/usr/bin/env python3
"""Evaluation harness for the Investment Research Evidence Agent.

Runs the full research pipeline over a fixed dataset of questions against
synthetic fixture filings (offline and deterministic — safe for CI), then
reports:

- citation validity        excerpts that verifiably appear in the cited source
- claim support rate       claims judged supported / partially supported
- unsupported-claim rate   claims blocked by verification
- blocked-claim leakage    blocked excerpts that leaked into a brief (must be 0)
- retrieval relevance      selected sections that match hand-labeled expectations
- verification agreement   verifier verdicts vs hand-labeled probe claims,
                           including a fabricated citation that must be blocked
- completion time          wall-clock seconds per research request

Usage:
    python eval/run_eval.py            # run and print a summary
    python eval/run_eval.py --check    # also exit non-zero if thresholds fail

Set LLM_PROVIDER=anthropic (with ANTHROPIC_API_KEY) to evaluate the real model
on the same harness; the default is the deterministic mock.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any app import: settings and engine are built at import.
os.environ.setdefault("LLM_PROVIDER", "mock")
_tmpdir = tempfile.mkdtemp(prefix="irea-eval-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/eval.db"

from app.agents.orchestrator import Orchestrator  # noqa: E402
from app.agents.retrieval import FilingRetrievalAgent  # noqa: E402
from app.agents.verification import VerificationAgent  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import AuditEvent, Filing, ResearchRequest  # noqa: E402
from app.llm.base import get_provider  # noqa: E402
from app.schemas.agent_io import EvidenceItem  # noqa: E402
from app.services.sec_client import CompanyMatch, FilingRef  # noqa: E402
from app.services.textutil import normalize_for_match  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
DATASET = json.loads((Path(__file__).parent / "dataset.json").read_text())

COMPANIES = {
    "EXCO": CompanyMatch(cik="0000012345", ticker="EXCO", name="ExampleCo Inc."),
    "NVTK": CompanyMatch(cik="0000067890", ticker="NVTK", name="NovaTech Semiconductor Corp."),
}

FILINGS = {
    "exco-10k": ("EXCO", FilingRef(
        accession_number="0000012345-24-000001", form_type="10-K",
        filing_date=date(2024, 2, 15), period_of_report=date(2023, 12, 31),
        primary_doc="exco-10k.htm",
        primary_doc_url="https://fixtures.local/exampleco_10k_fy2023.html")),
    "exco-10q": ("EXCO", FilingRef(
        accession_number="0000012345-24-000055", form_type="10-Q",
        filing_date=date(2024, 8, 5), period_of_report=date(2024, 6, 30),
        primary_doc="exco-10q.htm",
        primary_doc_url="https://fixtures.local/exampleco_10q_q2_2024.html")),
    "nvtk-10k": ("NVTK", FilingRef(
        accession_number="0000067890-24-000012", form_type="10-K",
        filing_date=date(2024, 2, 28), period_of_report=date(2023, 12, 31),
        primary_doc="nvtk-10k.htm",
        primary_doc_url="https://fixtures.local/novatech_10k_fy2023.html")),
}


class EvalSecClient:
    """Serves the fixture corpus instead of live EDGAR."""

    def search_companies(self, query, limit=10):
        return list(COMPANIES.values())

    def list_filings(self, cik, forms=None, limit=20):
        return [ref for _, (tkr, ref) in FILINGS.items()
                if COMPANIES[tkr].cik == cik]

    def fetch_document(self, url: str) -> str:
        return (FIXTURES / url.rsplit("/", 1)[-1]).read_text()


_ITEM_KEY_RE = re.compile(r"Item ([A-Z0-9-]+)\.")


def _selected_item_keys(db, request_id: int) -> list[str]:
    event = (db.query(AuditEvent)
             .filter(AuditEvent.request_id == request_id,
                     AuditEvent.event_type == "sections_selected")
             .first())
    if event is None:
        return []
    names = json.loads(event.payload_json).get("sections", [])
    keys = []
    for name in names:
        match = _ITEM_KEY_RE.search(name)
        keys.append(match.group(1) if match else "?")
    return keys


def run() -> dict:
    init_db()
    sec = EvalSecClient()
    retrieval = FilingRetrievalAgent(sec)
    provider = get_provider()
    orchestrator = Orchestrator(provider, sec)

    db = SessionLocal()
    filing_ids: dict[str, int] = {}
    for key, (ticker, ref) in FILINGS.items():
        company = COMPANIES[ticker]
        filings = retrieval.list_filings(db, company.cik, company.ticker, company.name)
        filing = next(f for f in filings if f.accession_number == ref.accession_number)
        retrieval.ingest_filing(db, filing)
        filing_ids[key] = filing.id

    # ---- pipeline questions -------------------------------------------------
    per_question = []
    for entry in DATASET["questions"]:
        request = ResearchRequest(
            filing_id=filing_ids[entry["filing"]],
            compare_filing_id=filing_ids.get(entry.get("compare_filing")),
            question=entry["question"],
            task_type=entry["task_type"],
        )
        db.add(request)
        db.commit()

        started = time.perf_counter()
        orchestrator.run_research(request.id)
        duration = time.perf_counter() - started

        db.expire_all()
        request = db.get(ResearchRequest, request.id)
        evidence = request.evidence
        brief = max(request.briefs, key=lambda b: b.version, default=None)
        brief_text = normalize_for_match(brief.content_markdown) if brief else ""

        n = len(evidence)
        citation_valid = sum(1 for e in evidence
                             if e.verification and e.verification.citation_valid)
        supported = sum(1 for e in evidence if e.status == "verified")
        blocked = sum(1 for e in evidence if e.status == "blocked")
        leaks = sum(
            1 for e in evidence
            if e.status == "blocked"
            and normalize_for_match(e.excerpt)[:80] in brief_text
        )

        selected = _selected_item_keys(db, request.id)
        expected = set(entry["expected_items"])
        # Recall is the metric that matters for evidence work: did we include
        # the sections a human would look in? Precision is reported alongside
        # (extra sections dilute focus but the extractor can ignore them).
        recall = (sum(1 for k in expected if k in selected) / len(expected)
                  if expected else 0.0)
        precision = (sum(1 for k in selected if k in expected) / len(selected)
                     if selected else 0.0)

        per_question.append({
            "id": entry["id"], "status": request.status,
            "evidence": n, "citation_valid": citation_valid,
            "supported": supported, "blocked": blocked, "leaks": leaks,
            "selected_sections": selected,
            "retrieval_recall": round(recall, 3),
            "retrieval_precision": round(precision, 3),
            "seconds": round(duration, 3),
        })

    # ---- verification probes ------------------------------------------------
    verifier = VerificationAgent(provider)
    probe_results = []
    for probe in DATASET["verification_probes"]:
        filing = db.get(Filing, filing_ids[probe["filing"]])
        section = next((s for s in filing.sections
                        if s.item_key == probe["section_item"]), None)
        item = EvidenceItem(
            claim=probe["claim"], excerpt=probe["excerpt"],
            section_name=section.name, filing_date=filing.filing_date,
            accession_number=filing.accession_number,
            source_url=filing.primary_doc_url, confidence=0.9,
        )
        result = verifier.verify(item, section.text)
        outcome = result.verdict.value if verifier.passes(result) else "blocked"
        agreed = outcome in probe["expected"] or result.verdict.value in probe["expected"]
        probe_results.append({"id": probe["id"], "outcome": outcome,
                              "verdict": result.verdict.value,
                              "citation_valid": result.citation_valid,
                              "agreed": agreed})

    db.close()

    # ---- aggregate ------------------------------------------------------------
    total_evidence = sum(q["evidence"] for q in per_question)
    completed = [q for q in per_question if q["status"] == "awaiting_review"]
    summary = {
        "provider": provider.name,
        "questions": len(per_question),
        "completed": len(completed),
        "total_evidence": total_evidence,
        "citation_validity": round(
            sum(q["citation_valid"] for q in per_question) / total_evidence, 3)
            if total_evidence else None,
        "claim_support_rate": round(
            sum(q["supported"] for q in per_question) / total_evidence, 3)
            if total_evidence else None,
        "unsupported_claim_rate": round(
            sum(q["blocked"] for q in per_question) / total_evidence, 3)
            if total_evidence else None,
        "blocked_claim_leaks": sum(q["leaks"] for q in per_question),
        "retrieval_relevance": round(
            sum(q["retrieval_recall"] for q in per_question) / len(per_question), 3),
        "retrieval_precision": round(
            sum(q["retrieval_precision"] for q in per_question) / len(per_question), 3),
        "verification_agreement": round(
            sum(1 for p in probe_results if p["agreed"]) / len(probe_results), 3),
        "fabricated_probe_blocked": next(
            p["outcome"] == "blocked" for p in probe_results
            if p["id"].startswith("p01")),
        "mean_seconds": round(
            sum(q["seconds"] for q in per_question) / len(per_question), 3),
        "max_seconds": round(max(q["seconds"] for q in per_question), 3),
    }
    return {"summary": summary, "questions": per_question, "probes": probe_results}


def print_report(report: dict) -> None:
    s = report["summary"]
    print("\n=== Investment Research Evidence Agent — Evaluation ===")
    print(f"Provider: {s['provider']}\n")
    print(f"{'ID':6} {'status':16} {'evid':>4} {'valid':>5} {'supp':>4} "
          f"{'blkd':>4} {'rec':>5} {'prec':>5} {'sec':>6}  selected")
    for q in report["questions"]:
        print(f"{q['id']:6} {q['status']:16} {q['evidence']:>4} "
              f"{q['citation_valid']:>5} {q['supported']:>4} {q['blocked']:>4} "
              f"{q['retrieval_recall']:>5} {q['retrieval_precision']:>5} "
              f"{q['seconds']:>6}  {','.join(q['selected_sections'])}")
    print("\nVerification probes:")
    for p in report["probes"]:
        flag = "OK " if p["agreed"] else "MISS"
        print(f"  [{flag}] {p['id']:26} -> {p['outcome']} "
              f"(citation_valid={p['citation_valid']})")
    print("\nSummary:")
    for key, value in s.items():
        print(f"  {key:26} {value}")
    print()


THRESHOLDS = {
    "citation_validity": 0.95,       # >=
    "claim_support_rate": 0.60,      # >=
    "retrieval_relevance": 0.75,     # >= (recall of expected sections)
    "verification_agreement": 0.75,  # >=
}


def check(report: dict) -> int:
    s = report["summary"]
    failures = []
    for metric, minimum in THRESHOLDS.items():
        if s[metric] is None or s[metric] < minimum:
            failures.append(f"{metric}={s[metric]} < {minimum}")
    if s["blocked_claim_leaks"] != 0:
        failures.append(f"blocked_claim_leaks={s['blocked_claim_leaks']} != 0")
    if not s["fabricated_probe_blocked"]:
        failures.append("fabricated citation probe was NOT blocked")
    if s["completed"] != s["questions"]:
        failures.append(f"only {s['completed']}/{s['questions']} runs completed")
    if failures:
        print("EVALUATION FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All evaluation thresholds passed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if quality thresholds are not met")
    args = parser.parse_args()

    report = run()
    print_report(report)

    out_dir = Path(__file__).parent / "eval_results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "summary.json"
    out_file.write_text(json.dumps(report, indent=2))
    print(f"Full results written to {out_file}")

    if args.check:
        sys.exit(check(report))
