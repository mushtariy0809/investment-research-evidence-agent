"""Research workflow endpoints: create a request, poll its status, review it."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_orchestrator
from app.db.database import get_db
from app.db.models import Filing, HumanReview, ResearchRequest
from app.schemas.agent_io import TaskType
from app.schemas.api import (
    AgentRunOut,
    BriefOut,
    EvidenceOut,
    ResearchCreate,
    ResearchStatusOut,
    ReviewCreate,
)
from app.services import audit

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("", status_code=202)
def create_research(body: ResearchCreate, background: BackgroundTasks,
                    db: Session = Depends(get_db)):
    filing = db.get(Filing, body.filing_id)
    if filing is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    if body.compare_filing_id is not None:
        compare = db.get(Filing, body.compare_filing_id)
        if compare is None:
            raise HTTPException(status_code=404, detail="Comparison filing not found")
        if compare.id == filing.id:
            raise HTTPException(status_code=422,
                                detail="Comparison filing must differ from the main filing")
    if body.task_type == TaskType.MATERIAL_CHANGES and body.compare_filing_id is None:
        raise HTTPException(status_code=422,
                            detail="material_changes requires compare_filing_id")

    request = ResearchRequest(
        filing_id=body.filing_id,
        compare_filing_id=body.compare_filing_id,
        question=body.question,
        task_type=body.task_type.value,
        status="pending",
    )
    db.add(request)
    db.commit()
    audit.record_event(db, "human", "research_requested",
                       {"question": body.question, "task_type": body.task_type.value},
                       request.id)
    background.add_task(get_orchestrator().run_research, request.id)
    return {"id": request.id, "status": request.status}


@router.get("", response_model=list[dict])
def list_research(db: Session = Depends(get_db)):
    requests = db.execute(
        select(ResearchRequest).order_by(ResearchRequest.id.desc()).limit(50)
    ).scalars().all()
    return [
        {"id": r.id, "status": r.status, "question": r.question,
         "task_type": r.task_type, "created_at": r.created_at.isoformat()}
        for r in requests
    ]


@router.get("/{request_id}", response_model=ResearchStatusOut)
def get_research(request_id: int, db: Session = Depends(get_db)):
    request = db.get(ResearchRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Research request not found")

    evidence_out = []
    for row in request.evidence:
        verification = row.verification
        evidence_out.append(EvidenceOut(
            id=row.id, claim=row.claim, excerpt=row.excerpt,
            section_name=row.section_name, filing_date=row.filing_date,
            accession_number=row.accession_number, source_url=row.source_url,
            confidence=row.confidence, status=row.status,
            verdict=verification.verdict if verification else None,
            citation_valid=verification.citation_valid if verification else None,
            verification_explanation=verification.explanation if verification else None,
        ))

    latest_brief = max(request.briefs, key=lambda b: b.version, default=None)
    return ResearchStatusOut(
        id=request.id, status=request.status, task_type=request.task_type,
        question=request.question, filing_id=request.filing_id,
        compare_filing_id=request.compare_filing_id, error=request.error,
        agent_runs=[AgentRunOut.model_validate(r) for r in request.agent_runs],
        evidence=evidence_out,
        brief=BriefOut.model_validate(latest_brief) if latest_brief else None,
        missing_info_note=request.missing_info_note,
    )


@router.post("/{request_id}/review")
def review_research(request_id: int, body: ReviewCreate, db: Session = Depends(get_db)):
    """Human decision gate — a brief is never final without one."""
    request = db.get(ResearchRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Research request not found")
    if request.status != "awaiting_review":
        raise HTTPException(
            status_code=409,
            detail=f"Request is '{request.status}', not awaiting review",
        )
    latest_brief = max(request.briefs, key=lambda b: b.version, default=None)
    if latest_brief is None:
        raise HTTPException(status_code=409, detail="No brief exists to review")

    db.add(HumanReview(request_id=request.id, brief_id=latest_brief.id,
                       decision=body.decision, comment=body.comment))
    audit.record_event(db, "human", f"review_{body.decision}",
                       {"brief_version": latest_brief.version, "comment": body.comment},
                       request.id)

    if body.decision == "revision_requested":
        brief = get_orchestrator().revise_brief(db, request, body.comment)
        return {"status": request.status, "brief_version": brief.version}

    request.status = body.decision
    db.commit()
    return {"status": request.status, "brief_version": latest_brief.version}
