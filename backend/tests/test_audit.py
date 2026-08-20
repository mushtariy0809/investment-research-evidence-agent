from app.db.models import AuditEvent
from app.services.audit import record_event, verify_chain


def test_chain_intact_after_multiple_events(db):
    for i in range(5):
        record_event(db, "system", f"event_{i}", {"index": i})
    intact, count, broken = verify_chain(db)
    assert intact and count == 5 and broken is None


def test_events_are_chained(db):
    first = record_event(db, "system", "first")
    second = record_event(db, "system", "second")
    assert second.prev_hash == first.hash
    assert first.hash != second.hash


def test_tampering_is_detected(db):
    record_event(db, "system", "original", {"value": 1})
    record_event(db, "system", "later")
    # Simulate an attacker editing history directly in the database.
    row = db.query(AuditEvent).first()
    row.payload_json = '{"value": 999}'
    db.commit()
    intact, _, broken = verify_chain(db)
    assert intact is False
    assert broken == row.id
