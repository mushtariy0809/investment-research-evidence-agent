"""Request/response models for the HTTP API (what the frontend sees)."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.agent_io import TaskType


class CompanyOut(BaseModel):
    cik: str
    ticker: str
    name: str


class FilingOut(BaseModel):
    id: int
    accession_number: str
    form_type: str
    filing_date: date
    period_of_report: date | None
    primary_doc_url: str
    downloaded: bool
    section_count: int = 0

    model_config = {"from_attributes": True}


class SectionOut(BaseModel):
    item_key: str
    name: str
    char_count: int

    model_config = {"from_attributes": True}


class ResearchCreate(BaseModel):
    filing_id: int
    task_type: TaskType
    question: str = Field(min_length=5, max_length=500)
    compare_filing_id: int | None = None

    @field_validator("question")
    @classmethod
    def question_is_plain_text(cls, v: str) -> str:
        # Basic input validation: reject control characters and obvious markup.
        if any(ord(c) < 32 and c not in "\n\t" for c in v):
            raise ValueError("question contains control characters")
        return v.strip()


class EvidenceOut(BaseModel):
    id: int
    claim: str
    excerpt: str
    section_name: str
    filing_date: date
    accession_number: str
    source_url: str
    confidence: float
    status: str
    verdict: str | None = None
    citation_valid: bool | None = None
    verification_explanation: str | None = None


class AgentRunOut(BaseModel):
    agent_name: str
    status: str
    input_summary: str
    output_summary: str
    error: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class BriefOut(BaseModel):
    id: int
    content_markdown: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ResearchStatusOut(BaseModel):
    id: int
    status: str
    task_type: str
    question: str
    filing_id: int
    compare_filing_id: int | None
    error: str | None
    agent_runs: list[AgentRunOut]
    evidence: list[EvidenceOut]
    brief: BriefOut | None
    missing_info_note: str | None = None


class ReviewCreate(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|revision_requested)$")
    comment: str = Field(default="", max_length=2000)


class AuditEventOut(BaseModel):
    id: int
    request_id: int | None
    actor: str
    event_type: str
    payload_json: str
    prev_hash: str
    hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditVerifyOut(BaseModel):
    intact: bool
    events_checked: int
    first_broken_id: int | None = None
