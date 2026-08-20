"""SQLAlchemy ORM models.

Design notes:
- Enum-like fields are stored as short strings (validated at the API layer by
  Pydantic) rather than DB enums, so adding a value never needs a migration.
- AuditEvent is append-only: no code path updates or deletes rows, and each
  row carries a SHA-256 hash chained to the previous row so tampering with
  history is detectable.
"""

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    # Naive UTC on purpose: SQLite stores datetimes without a timezone, so a
    # tz-aware value would come back different from what was written — which
    # would silently break the audit trail's hash chain on re-verification.
    return datetime.now(UTC).replace(tzinfo=None)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # zero-padded
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    filings: Mapped[list["Filing"]] = relationship(back_populates="company")


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession_number: Mapped[str] = mapped_column(String(25), unique=True, index=True)
    form_type: Mapped[str] = mapped_column(String(10))  # "10-K" | "10-Q"
    filing_date: Mapped[date] = mapped_column(Date)
    period_of_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_doc_url: Mapped[str] = mapped_column(String(500))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)

    company: Mapped[Company] = relationship(back_populates="filings")
    sections: Mapped[list["FilingSection"]] = relationship(
        back_populates="filing", order_by="FilingSection.position"
    )


class FilingSection(Base):
    __tablename__ = "filing_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(10))  # e.g. "1A", "7", "FULL"
    name: Mapped[str] = mapped_column(String(255))  # e.g. "Item 1A. Risk Factors"
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)  # order within the filing

    filing: Mapped[Filing] = relationship(back_populates="sections")


class ResearchRequest(Base):
    __tablename__ = "research_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)
    # Optional second filing for "what changed?" comparisons.
    compare_filing_id: Mapped[int | None] = mapped_column(
        ForeignKey("filings.id"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(40))  # business_overview, risk_factors, ...
    # pending -> running -> awaiting_review -> approved | rejected | revision_requested
    # (or -> failed at any point)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when the extraction agent reports the filing does not answer the question.
    missing_info_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    filing: Mapped[Filing] = relationship(foreign_keys=[filing_id])
    compare_filing: Mapped[Filing | None] = relationship(foreign_keys=[compare_filing_id])
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="request")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="request")
    briefs: Mapped[list["ResearchBrief"]] = relationship(back_populates="request")
    reviews: Mapped[list["HumanReview"]] = relationship(back_populates="request")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("research_requests.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|succeeded|failed
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    request: Mapped[ResearchRequest] = relationship(back_populates="agent_runs")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("research_requests.id"), index=True)
    claim: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)  # verbatim quote from the filing
    section_name: Mapped[str] = mapped_column(String(255))
    filing_date: Mapped[date] = mapped_column(Date)
    accession_number: Mapped[str] = mapped_column(String(25))
    source_url: Mapped[str] = mapped_column(String(500))
    confidence: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0, from the extraction agent
    # proposed -> verified | blocked (set by the verification step)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    request: Mapped[ResearchRequest] = relationship(back_populates="evidence")
    verification: Mapped["ClaimVerification | None"] = relationship(back_populates="evidence")


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), unique=True)
    # supported | partially_supported | unsupported | contradicted
    verdict: Mapped[str] = mapped_column(String(25))
    citation_valid: Mapped[bool] = mapped_column(Boolean)  # excerpt found verbatim in source
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    evidence: Mapped[Evidence] = relationship(back_populates="verification")


class ResearchBrief(Base):
    __tablename__ = "research_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("research_requests.id"), index=True)
    content_markdown: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)  # bumped on each revision
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    request: Mapped[ResearchRequest] = relationship(back_populates="briefs")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("research_requests.id"), index=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("research_briefs.id"))
    decision: Mapped[str] = mapped_column(String(25))  # approved|rejected|revision_requested
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    request: Mapped[ResearchRequest] = relationship(back_populates="reviews")


class AuditEvent(Base):
    """Append-only audit trail. Rows are only ever inserted.

    Each row stores hash = SHA-256(prev_hash + actor + event_type + payload +
    timestamp), forming a chain: editing or deleting any historical row breaks
    every hash after it, which /api/audit/verify detects.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_requests.id"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(50))  # system | human | <agent name>
    event_type: Mapped[str] = mapped_column(String(60))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
