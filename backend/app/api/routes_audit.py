"""Audit trail endpoints: read the append-only log, verify chain integrity."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AuditEvent
from app.schemas.api import AuditEventOut, AuditVerifyOut
from app.services.audit import verify_chain

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(request_id: int | None = Query(default=None),
                      limit: int = Query(default=200, le=1000),
                      db: Session = Depends(get_db)):
    stmt = select(AuditEvent).order_by(AuditEvent.id)
    if request_id is not None:
        stmt = stmt.where(AuditEvent.request_id == request_id)
    return db.execute(stmt.limit(limit)).scalars().all()


@router.get("/verify", response_model=AuditVerifyOut)
def verify_audit_chain(db: Session = Depends(get_db)):
    intact, count, first_broken = verify_chain(db)
    return AuditVerifyOut(intact=intact, events_checked=count, first_broken_id=first_broken)
