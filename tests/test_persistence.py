"""
tests/test_persistence.py - Verification of SQLite persistence.

Verifies:
- Answer, verdict, question, and record history survive program exit.
- Reads full history by concept (never only the latest row).
- Multi-encounter audit logs are completely preserved.
"""

import tempfile
from pathlib import Path
import pytest

from models import Answer, ConceptRecord, Outcome, State, Verdict
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_persistence.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_full_event_history_persistence(temp_store):
    """Verifies that all events are appended and readable in order."""
    session_id = "test-session-persist-1"

    # Append sequential events
    temp_store.append_event(session_id, 1, State.PROMPTING, "QUESTION_LOADED", {"concept": "recursion_base_case"})
    temp_store.append_event(session_id, 2, State.ANSWERING, "ANSWER_SUBMITTED", {"answer": "return 1", "rating": 4})
    temp_store.append_event(session_id, 3, State.CHECKING, "VERDICT_ISSUED", {"passed": False, "mismatch": True})
    temp_store.append_event(session_id, 4, State.WAITING_FOR_FOLLOWUP, "FOLLOWUP_REQUESTED", {"prompt": "Why return 1?"})
    temp_store.append_event(session_id, 5, State.CHECKING, "FOLLOWUP_SUBMITTED", {"answer": "return 0", "rating": 4})
    temp_store.append_event(session_id, 6, State.RECORDED, "RECORD_SAVED", {"confidence": 3, "outcome": "resolved_on_follow_up"})

    events = temp_store.get_session_events(session_id)
    assert len(events) == 6
    assert events[0].state == State.PROMPTING
    assert events[1].state == State.ANSWERING
    assert events[2].state == State.CHECKING
    assert events[3].state == State.WAITING_FOR_FOLLOWUP
    assert events[4].state == State.CHECKING
    assert events[5].state == State.RECORDED

    # Re-instantiating store with the same db file verifies persistence across process restarts
    new_store_instance = MindMeshStore(db_path=temp_store.db_path)
    reloaded_events = new_store_instance.get_session_events(session_id)
    assert len(reloaded_events) == 6
    assert reloaded_events[-1].payload["outcome"] == "resolved_on_follow_up"


def test_concept_records_history_multi_encounter(temp_store):
    """Verifies reading full history by concept (never only the latest row)."""
    from datetime import datetime, timedelta, timezone

    concept_id = "recursion_base_case"
    now = datetime.now(timezone.utc)

    # Encounter 1: resolved on follow-up
    rec1 = ConceptRecord(
        concept_id=concept_id,
        session_id="session-enc-1",
        confidence=3,
        outcome=Outcome.RESOLVED_ON_FOLLOW_UP,
        attempts_count=2,
        next_review_at=now + timedelta(days=2),
        created_at=now,
    )
    temp_store.save_concept_record(rec1)

    # Encounter 2: first try correct
    rec2 = ConceptRecord(
        concept_id=concept_id,
        session_id="session-enc-2",
        confidence=5,
        outcome=Outcome.FIRST_TRY_CORRECT,
        attempts_count=1,
        next_review_at=now + timedelta(days=7),
        created_at=now + timedelta(days=2),
    )
    temp_store.save_concept_record(rec2)

    # Must return all historical encounters, not only latest
    history = temp_store.get_concept_records(concept_id)
    assert len(history) == 2
    assert history[0].session_id == "session-enc-1"
    assert history[0].outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert history[1].session_id == "session-enc-2"
    assert history[1].outcome == Outcome.FIRST_TRY_CORRECT

    # Latest record check
    latest = temp_store.get_latest_concept_record(concept_id)
    assert latest is not None
    assert latest.session_id == "session-enc-2"
    assert latest.confidence == 5


def test_flush_guest_data(temp_store):
    """Verifies that flush_guest_data purges guest records/events without affecting registered users."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    # Guest record and event
    guest_rec = ConceptRecord(
        concept_id="recursion",
        session_id="guest-sess-1",
        user_id="default_student",
        confidence=4,
        outcome=Outcome.FIRST_TRY_CORRECT,
        attempts_count=1,
        next_review_at=now + timedelta(days=3),
        created_at=now,
    )
    temp_store.save_concept_record(guest_rec)
    temp_store.append_event("guest-sess-1", 1, State.RECORDED, "RECORD_SAVED", {}, user_id="default_student")

    # Registered user record and event
    alice_rec = ConceptRecord(
        concept_id="recursion",
        session_id="alice-sess-1",
        user_id="alice",
        confidence=5,
        outcome=Outcome.FIRST_TRY_CORRECT,
        attempts_count=1,
        next_review_at=now + timedelta(days=7),
        created_at=now,
    )
    temp_store.save_concept_record(alice_rec)
    temp_store.append_event("alice-sess-1", 1, State.RECORDED, "RECORD_SAVED", {}, user_id="alice")

    assert len(temp_store.get_user_records("default_student")) == 1
    assert len(temp_store.get_user_records("alice")) == 1

    # Flush guest data
    deleted_count = temp_store.flush_guest_data()
    assert deleted_count == 1

    # Guest records and events must now be empty
    assert len(temp_store.get_user_records("default_student")) == 0
    assert len(temp_store.get_all_session_events(user_id="default_student")) == 0

    # Alice's records must remain intact
    alice_records = temp_store.get_user_records("alice")
    assert len(alice_records) == 1
    assert alice_records[0].session_id == "alice-sess-1"
    assert len(temp_store.get_all_session_events(user_id="alice")) == 1

