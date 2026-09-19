"""
tests/test_second_encounter.py - Verification of spaced repetition and second encounter.

Verifies:
- Encounter 1: Mismatch -> Follow-up -> Resolved -> Next review scheduled for +2 days.
- Fast-forward clock in debug mode to make review due.
- Encounter 2: Reopen concept, system recalls prior history.
- Student succeeds on first try with 5/5 -> Next review scheduled for +7 days.
- Full encounter progression is queryable in SQLite.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from decay import fast_forward_record, is_due_for_review
from flow import FlowSession
from models import Outcome, State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_second_encounter.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_two_encounter_progression_and_decay(temp_store):
    """Verifies the complete two-encounter lifecycle matching demo beats 1-8."""

    # === ENCOUNTER 1: Mismatch and follow-up ===
    s1 = FlowSession(session_id="session-enc-1", store=temp_store)
    step_prompting(s1)
    # Student gives wrong answer, self-rates 4/5
    step_answering(s1, "if len(numbers) == 0: return 1", self_rating=4)
    step_checking(s1)
    assert s1.state == State.WAITING_FOR_FOLLOWUP

    # Corrected on follow-up
    step_followup(s1, "if not numbers: return 0")
    step_checking(s1)
    assert s1.state == State.RECORDED

    # Encounter 1 recorded with confidence 3, resolved on follow-up
    rec1 = temp_store.get_latest_concept_record("recursion_base_case")
    assert rec1 is not None
    assert rec1.outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert rec1.confidence == 3
    assert not is_due_for_review(rec1)  # Scheduled 2 days out

    # === BEAT 7: FAST-FORWARD CLOCK IN DEBUG MODE ===
    ff_rec = fast_forward_record(rec1, hours=72.0)
    temp_store.save_concept_record(ff_rec)
    assert is_due_for_review(ff_rec)

    # === BEAT 8: ENCOUNTER 2: REOPEN CONCEPT ===
    s2 = FlowSession(session_id="session-enc-2", store=temp_store)
    step_prompting(s2)

    # Check that s2 received prior history in the loaded event
    events = temp_store.get_session_events("session-enc-2")
    loaded_event = events[0]
    assert loaded_event.event_type == "QUESTION_LOADED"
    prior_info = loaded_event.payload.get("prior_history")
    assert prior_info is not None
    assert prior_info["previous_encounters"] == 1
    assert prior_info["last_outcome"] == "resolved_on_follow_up"
    assert prior_info["last_confidence"] == 3

    # Student demonstrates mastery: answers correctly on first try with 5/5, then provides verified explanation
    step_answering(s2, "B", self_rating=5)
    step_checking(s2)
    assert s2.state == State.WAITING_FOR_FOLLOWUP
    step_followup(s2, "An empty list has length 0, so the recursive sum must return 0 as the additive identity.")
    step_checking(s2)
    assert s2.state == State.RECORDED

    # Final concept record shows mastery progression
    all_records = temp_store.get_concept_records("recursion_base_case")
    assert len(all_records) == 2
    assert all_records[0].outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert all_records[1].outcome == Outcome.FIRST_TRY_CORRECT
    assert all_records[1].confidence == 5
