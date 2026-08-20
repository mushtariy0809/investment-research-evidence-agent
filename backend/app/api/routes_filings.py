"""Company search and filing retrieval endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_retrieval_agent
from app.db.database import get_db
from app.db.models import Filing, FilingSection
from app.schemas.api import CompanyOut, FilingOut, SectionOut
from app.services.sec_client import SecError

router = APIRouter(prefix="/api", tags=["filings"])


@router.get("/companies/search", response_model=list[CompanyOut])
def search_companies(q: str = Query(min_length=1, max_length=50)):
    try:
        matches = get_retrieval_agent().search_companies(q)
    except SecError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [CompanyOut(cik=m.cik, ticker=m.ticker, name=m.name) for m in matches]


@router.get("/companies/{cik}/filings", response_model=list[FilingOut])
def list_filings(cik: str, ticker: str = "", name: str = "",
                 db: Session = Depends(get_db)):
    if not (cik.isdigit() and len(cik) <= 10):
        raise HTTPException(status_code=422, detail="CIK must be numeric")
    try:
        filings = get_retrieval_agent().list_filings(db, cik.zfill(10), ticker, name)
    except SecError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    counts = dict(
        db.execute(
            select(FilingSection.filing_id, func.count())
            .group_by(FilingSection.filing_id)
        ).all()
    )
    return [
        FilingOut(
            id=f.id,
            accession_number=f.accession_number,
            form_type=f.form_type,
            filing_date=f.filing_date,
            period_of_report=f.period_of_report,
            primary_doc_url=f.primary_doc_url,
            downloaded=f.downloaded_at is not None,
            section_count=counts.get(f.id, 0),
        )
        for f in filings
    ]


@router.post("/filings/{filing_id}/ingest", response_model=list[SectionOut])
def ingest_filing(filing_id: int, db: Session = Depends(get_db)):
    """Download and parse the filing into sections (cached after first call)."""
    filing = db.get(Filing, filing_id)
    if filing is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    try:
        sections = get_retrieval_agent().ingest_filing(db, filing)
    except SecError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sections
