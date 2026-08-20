"""Orchestrator Agent.

Coordinates the research workflow: selects relevant sections, runs extraction,
verification, and brief writing, tracks every step as an AgentRun row, and
appends everything to the audit trail. It draws no financial conclusions of
its own — it only routes typed data between agents, and by construction it
hands the brief writer only evidence that passed verification.

It runs in a background thread (FastAPI BackgroundTasks), so it opens its own
database session rather than borrowing a request-scoped one.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.brief_writer import AGENT_NAME as BRIEF_AGENT
from app.agents.brief_writer import BriefWriterAgent
from app.agents.extraction import AGENT_NAME as EXTRACT_AGENT
from app.agents.extraction import EvidenceExtractionAgent, FilingMeta
from app.agents.retrieval import FilingRetrievalAgent
from app.agents.verification import AGENT_NAME as VERIFY_AGENT
from app.agents.verification import VerificationAgent
from app.db.database import SessionLocal
from app.db.models import (
    AgentRun,
    ClaimVerification,
    Evidence,
    Filing,
    ResearchBrief,
    ResearchRequest,
    utcnow,
)
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.schemas.agent_io import BriefInput, SectionInput, TaskType, Verdict
from app.services import audit
from app.services.relevance import rank_sections
from app.services.sec_client import SecClient

logger = get_logger(__name__)

ORCHESTRATOR = "orchestrator"


class Orchestrator:
    def __init__(self, provider: LLMProvider, sec_client: SecClient):
        self._extraction = EvidenceExtractionAgent(provider)
        self._verification = VerificationAgent(provider)
        self._brief_writer = BriefWriterAgent(provider)
        self._retrieval = FilingRetrievalAgent(sec_client)

    # -- AgentRun bookkeeping ----------------------------------------------

    @staticmethod
    def _start_run(db: Session, request_id: int, agent: str, input_summary: str) -> AgentRun:
        run = AgentRun(request_id=request_id, agent_name=agent, input_summary=input_summary)
        db.add(run)
        db.commit()
        return run

    @staticmethod
    def _finish_run(db: Session, run: AgentRun, output_summary: str,
                    error: str | None = None) -> None:
        run.status = "failed" if error else "succeeded"
        run.output_summary = output_summary
        run.error = error
        run.finished_at = utcnow()
        db.commit()

    # -- main pipeline -------------------------------------------------------

    def run_research(self, request_id: int) -> None:
        db = SessionLocal()
        try:
            request = db.get(ResearchRequest, request_id)
            if request is None:
                return
            request.status = "running"
            db.commit()
            audit.record_event(db, ORCHESTRATOR, "research_started",
                               {"question": request.question, "task_type": request.task_type},
                               request_id)
            self._pipeline(db, request)
        except Exception as exc:  # any failure ends the request in a visible state
            logger.exception("Research pipeline failed")
            db.rollback()
            request = db.get(ResearchRequest, request_id)
            if request is not None:
                request.status = "failed"
                request.error = str(exc)[:2000]
                db.commit()
                audit.record_event(db, ORCHESTRATOR, "research_failed",
                                   {"error": str(exc)[:500]}, request_id)
        finally:
            db.close()

    def _pipeline(self, db: Session, request: ResearchRequest) -> None:
        task_type = TaskType(request.task_type)

        # 1) Make sure filings are ingested, then select relevant sections.
        sections, metas = self._prepare_sections(db, request, task_type)
        audit.record_event(
            db, ORCHESTRATOR, "sections_selected",
            {"sections": [f"{s.filing_label}: {s.name}" for s in sections]},
            request.id,
        )
        # 2) Extraction.
        run = self._start_run(
            db, request.id, EXTRACT_AGENT,
            f"question={request.question!r}, sections={len(sections)}",
        )
        try:
            result, warnings = self._extraction.run(
                request.question, task_type, sections, metas
            )
        except Exception as exc:
            self._finish_run(db, run, "", error=str(exc)[:2000])
            raise
        self._finish_run(
            db, run,
            f"{len(result.evidence)} evidence item(s); "
            f"missing_info={result.missing_info_note!r}",
        )
        for warning in warnings:
            audit.record_event(db, EXTRACT_AGENT, "injection_warning",
                               {"detail": warning}, request.id)
        request.missing_info_note = result.missing_info_note
        db.commit()

        evidence_rows: list[Evidence] = []
        for item in result.evidence:
            row = Evidence(
                request_id=request.id,
                claim=item.claim,
                excerpt=item.excerpt,
                section_name=item.section_name,
                filing_date=item.filing_date,
                accession_number=item.accession_number,
                source_url=item.source_url,
                confidence=item.confidence,
                status="proposed",
            )
            db.add(row)
            evidence_rows.append(row)
        db.commit()
        audit.record_event(db, EXTRACT_AGENT, "evidence_extracted",
                           {"count": len(evidence_rows)}, request.id)

        # 3) Verification — every claim, no exceptions.
        run = self._start_run(db, request.id, VERIFY_AGENT,
                              f"{len(evidence_rows)} claim(s) to verify")
        verified_items, verified_verdicts = [], []
        blocked = 0
        try:
            for row, item in zip(evidence_rows, result.evidence, strict=True):
                source_text = self._find_source_text(db, item.accession_number,
                                                     item.section_name)
                verdict = self._verification.verify(item, source_text)
                db.add(ClaimVerification(
                    evidence_id=row.id,
                    verdict=verdict.verdict.value,
                    citation_valid=verdict.citation_valid,
                    explanation=verdict.explanation,
                ))
                if self._verification.passes(verdict):
                    row.status = "verified"
                    verified_items.append(item)
                    verified_verdicts.append(verdict.verdict)
                else:
                    row.status = "blocked"
                    blocked += 1
                db.commit()
                audit.record_event(
                    db, VERIFY_AGENT, "claim_verified",
                    {"evidence_id": row.id, "verdict": verdict.verdict.value,
                     "citation_valid": verdict.citation_valid,
                     "blocked": row.status == "blocked"},
                    request.id,
                )
        except Exception as exc:
            self._finish_run(db, run, "", error=str(exc)[:2000])
            raise
        self._finish_run(db, run, f"{len(verified_items)} passed, {blocked} blocked")

        # 4) Brief writing — verified evidence only.
        filing = db.get(Filing, request.filing_id)
        run = self._start_run(db, request.id, BRIEF_AGENT,
                              f"{len(verified_items)} verified evidence item(s)")
        try:
            if verified_items:
                markdown = self._brief_writer.run(BriefInput(
                    question=request.question,
                    task_type=task_type,
                    company_name=filing.company.name,
                    form_type=filing.form_type,
                    filing_date=filing.filing_date,
                    evidence=verified_items,
                    verdicts=verified_verdicts,
                ))
            else:
                markdown = self._brief_writer.insufficient_evidence_brief(
                    request.question, request.missing_info_note
                )
        except Exception as exc:
            self._finish_run(db, run, "", error=str(exc)[:2000])
            raise
        self._finish_run(db, run, f"brief of {len(markdown)} chars")

        db.add(ResearchBrief(request_id=request.id, content_markdown=markdown, version=1))
        request.status = "awaiting_review"
        db.commit()
        audit.record_event(db, BRIEF_AGENT, "brief_generated",
                           {"version": 1, "chars": len(markdown)}, request.id)

    # -- helpers -------------------------------------------------------------

    def _prepare_sections(
        self, db: Session, request: ResearchRequest, task_type: TaskType
    ) -> tuple[list[SectionInput], dict[str, FilingMeta]]:
        sections: list[SectionInput] = []
        metas: dict[str, FilingMeta] = {}

        pairs = [("current", request.filing_id)]
        if request.compare_filing_id:
            pairs.append(("previous", request.compare_filing_id))

        for label, filing_id in pairs:
            filing = db.get(Filing, filing_id)
            if filing is None:
                raise ValueError(f"Filing {filing_id} not found")
            stored = self._retrieval.ingest_filing(db, filing)  # no-op if cached
            top_n = 2 if request.compare_filing_id else 3
            relevant = rank_sections(request.question, task_type,
                                     filing.form_type, stored, top_n=top_n)
            if not relevant:  # fall back to the largest sections
                relevant = sorted(stored, key=lambda s: s.char_count, reverse=True)[:top_n]
            sections.extend(
                SectionInput(item_key=s.item_key, name=s.name,
                             text=s.text[:60_000], filing_label=label)
                for s in relevant
            )
            metas[label] = FilingMeta(
                label=label,
                form_type=filing.form_type,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                source_url=filing.primary_doc_url,
            )
        return sections, metas

    @staticmethod
    def _find_source_text(db: Session, accession_number: str,
                          section_name: str) -> str | None:
        filing = db.execute(
            select(Filing).where(Filing.accession_number == accession_number)
        ).scalar_one_or_none()
        if filing is None:
            return None
        for section in filing.sections:
            if section.name.strip().lower() == section_name.strip().lower():
                return section.text
        return None

    # -- human-review revision cycle -----------------------------------------

    def revise_brief(self, db: Session, request: ResearchRequest, comment: str) -> ResearchBrief:
        """Regenerate the brief from the SAME verified evidence, addressing the
        reviewer's comment. Evidence and verdicts are not re-litigated."""
        task_type = TaskType(request.task_type)
        filing = db.get(Filing, request.filing_id)

        verified_items, verdicts = [], []
        for row in request.evidence:
            if row.status != "verified" or row.verification is None:
                continue
            from app.schemas.agent_io import EvidenceItem  # local to avoid cycle noise

            verified_items.append(EvidenceItem(
                claim=row.claim, excerpt=row.excerpt, section_name=row.section_name,
                filing_date=row.filing_date, accession_number=row.accession_number,
                source_url=row.source_url, confidence=row.confidence,
            ))
            verdicts.append(Verdict(row.verification.verdict))

        run = self._start_run(db, request.id, BRIEF_AGENT,
                              f"revision requested: {comment[:200]!r}")
        try:
            if verified_items:
                markdown = self._brief_writer.run(BriefInput(
                    question=request.question, task_type=task_type,
                    company_name=filing.company.name, form_type=filing.form_type,
                    filing_date=filing.filing_date, evidence=verified_items,
                    verdicts=verdicts, reviewer_comment=comment,
                ))
            else:
                markdown = self._brief_writer.insufficient_evidence_brief(
                    request.question, request.missing_info_note
                )
        except Exception as exc:
            self._finish_run(db, run, "", error=str(exc)[:2000])
            raise
        self._finish_run(db, run, f"revised brief of {len(markdown)} chars")

        version = max((b.version for b in request.briefs), default=0) + 1
        brief = ResearchBrief(request_id=request.id, content_markdown=markdown,
                              version=version)
        db.add(brief)
        request.status = "awaiting_review"
        db.commit()
        audit.record_event(db, BRIEF_AGENT, "brief_revised",
                           {"version": version}, request.id)
        return brief
