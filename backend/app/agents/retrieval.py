"""Filing Retrieval Agent.

The only component allowed to talk to SEC EDGAR. It has no LLM access at all —
retrieval is deterministic data work, and giving it a model would only add a
place for errors. It caches everything it fetches in the database so each
filing is downloaded exactly once (SEC fair-access) and later research runs
are offline-reproducible.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, Filing, FilingSection, utcnow
from app.logging_config import get_logger
from app.services.filing_parser import html_to_text, split_sections
from app.services.sec_client import CompanyMatch, FilingRef, SecClient

logger = get_logger(__name__)

AGENT_NAME = "filing_retrieval"


class FilingRetrievalAgent:
    def __init__(self, sec_client: SecClient):
        self._sec = sec_client

    def search_companies(self, query: str) -> list[CompanyMatch]:
        return self._sec.search_companies(query)

    def list_filings(self, db: Session, cik: str, ticker: str, name: str) -> list[Filing]:
        """Fetch filing references from EDGAR and upsert them as Filing rows."""
        company = db.execute(
            select(Company).where(Company.cik == cik)
        ).scalar_one_or_none()
        if company is None:
            company = Company(cik=cik, ticker=ticker, name=name)
            db.add(company)
            db.flush()

        refs: list[FilingRef] = self._sec.list_filings(cik)
        filings: list[Filing] = []
        for ref in refs:
            filing = db.execute(
                select(Filing).where(Filing.accession_number == ref.accession_number)
            ).scalar_one_or_none()
            if filing is None:
                filing = Filing(
                    company_id=company.id,
                    accession_number=ref.accession_number,
                    form_type=ref.form_type,
                    filing_date=ref.filing_date,
                    period_of_report=ref.period_of_report,
                    primary_doc_url=ref.primary_doc_url,
                )
                db.add(filing)
            filings.append(filing)
        db.commit()
        return filings

    def ingest_filing(self, db: Session, filing: Filing) -> list[FilingSection]:
        """Download the filing document (once) and store its parsed sections."""
        existing = db.execute(
            select(FilingSection).where(FilingSection.filing_id == filing.id)
        ).scalars().all()
        if existing:
            return list(existing)

        logger.info(
            "Ingesting filing",
            extra={"extra_fields": {"accession": filing.accession_number}},
        )
        html = self._sec.fetch_document(filing.primary_doc_url)
        text = html_to_text(html)
        parsed = split_sections(text, filing.form_type)

        sections = [
            FilingSection(
                filing_id=filing.id,
                item_key=p.item_key,
                name=p.name,
                text=p.text,
                char_count=len(p.text),
                position=i,
            )
            for i, p in enumerate(parsed)
        ]
        db.add_all(sections)
        filing.downloaded_at = utcnow()
        filing.char_count = len(text)
        db.commit()
        return sections
