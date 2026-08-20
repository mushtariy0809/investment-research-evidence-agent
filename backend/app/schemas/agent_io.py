"""Structured inputs/outputs exchanged between agents.

These Pydantic models are the contract of the pipeline: every agent takes and
returns typed objects, never free-form text. That makes each agent unit-testable
and makes it impossible for, say, the brief writer to receive unverified text.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    BUSINESS_OVERVIEW = "business_overview"
    RISK_FACTORS = "risk_factors"
    REVENUE_SEGMENTS = "revenue_segments"
    MANAGEMENT_DISCUSSION = "management_discussion"
    MATERIAL_CHANGES = "material_changes"  # requires a comparison filing
    CUSTOM = "custom"


class Verdict(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


class SectionInput(BaseModel):
    """A filing section handed to the extraction agent. Text is untrusted data."""

    item_key: str
    name: str
    text: str
    filing_label: str = "current"  # "current" or "previous" (for comparisons)


class EvidenceItem(BaseModel):
    """One piece of evidence proposed by the extraction agent."""

    claim: str = Field(min_length=1, max_length=1000)
    excerpt: str = Field(min_length=1, max_length=2000)  # must be verbatim from the filing
    section_name: str
    filing_date: date
    accession_number: str
    source_url: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    evidence: list[EvidenceItem]
    # The agent must say explicitly when the filing does not answer the question,
    # instead of inventing something.
    missing_info_note: str | None = None


class VerificationResult(BaseModel):
    verdict: Verdict
    citation_valid: bool
    explanation: str


class BriefInput(BaseModel):
    """Only verified evidence reaches the brief writer — enforced by type."""

    question: str
    task_type: TaskType
    company_name: str
    form_type: str
    filing_date: date
    evidence: list[EvidenceItem]
    verdicts: list[Verdict]  # parallel to evidence; only supported/partial allowed
    reviewer_comment: str | None = None  # set when a human requested revisions
