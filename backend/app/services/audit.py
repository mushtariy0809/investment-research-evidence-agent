"""Append-only, hash-chained audit trail.

Every meaningful action (agent start/finish, verification verdicts, human
decisions) is recorded as an AuditEvent. Rows are never updated or deleted.
Each row's hash covers the previous row's hash, so any tampering with history
invalidates every later hash — verify_chain() detects that.
"""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

GENESIS_HASH = "0" * 64


def _compute_hash(prev_hash: str, actor: str, event_type: str, payload_json: str,
                  created_at_iso: str) -> str:
    material = f"{prev_hash}|{actor}|{event_type}|{payload_json}|{created_at_iso}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def record_event(
    db: Session,
    actor: str,
    event_type: str,
    payload: dict | None = None,
    request_id: int | None = None,
) -> AuditEvent:
    payload_json = json.dumps(payload or {}, default=str, sort_keys=True)
    last = db.execute(
        select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = last.hash if last else GENESIS_HASH

    event = AuditEvent(
        request_id=request_id,
        actor=actor,
        event_type=event_type,
        payload_json=payload_json,
        prev_hash=prev_hash,
        hash="",  # filled below once created_at is fixed
    )
    db.add(event)
    db.flush()  # assigns id and created_at default
    event.hash = _compute_hash(
        prev_hash, actor, event_type, payload_json, event.created_at.isoformat()
    )
    db.commit()
    return event


def verify_chain(db: Session) -> tuple[bool, int, int | None]:
    """Recompute every hash in order. Returns (intact, count, first_broken_id)."""
    events = db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    prev_hash = GENESIS_HASH
    for event in events:
        expected = _compute_hash(
            prev_hash, event.actor, event.event_type,
            event.payload_json, event.created_at.isoformat(),
        )
        if event.hash != expected or event.prev_hash != prev_hash:
            return False, len(events), event.id
        prev_hash = event.hash
    return True, len(events), None
