"""
tests/test_restart.py - Verification of crash recovery and session resumption.

Verifies:
- A session interrupted mid-way (e.g., during Waiting for follow-up) can be resumed.
- No history or answer records are lost.
- The session can continue from where it stopped and reach terminal Recorded state.
"""

import tempfile
from pathlib import Path
import pytest

from flow import FlowSession
from models import State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_restart.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_crash_and_resume_at_waiting_for_followup(temp_store):
    """
    Test scenario:
    1. Student starts session, answers wrong with 4/5 confidence.
    2. Evaluator triggers mismatch -> State is WAITING_FOR_FOLLOWUP.
    3. Program crashes / process exits.
    4. New process starts, calls FlowSession.resume(session_id).
    5. Verifies state is still WAITING_FOR_FOLLOWUP with attempt 1 preserved.
    6. Student submits follow-up answer in the new process.
    7. Session completes to RECORDED with confidence 3.
    """
    session_id = "resumable-session-999"

    # Process 1 runs:
    session1 = FlowSession(session_id=session_id, store=temp_store)
    step_prompting(session1)
    step_answering(session1, "if len(numbers) == 0: return 1", self_rating=4)
    step_checking(session1)

    assert session1.state == State.WAITING_FOR_FOLLOWUP
    assert session1.attempt_count == 1

    # SIMULATE PROCESS KILL: session1 is discarded
    del session1

    # Process 2 starts: new store instance pointing to same db
    restored_store = MindMeshStore(db_path=temp_store.db_path)
    session2 = FlowSession.resume(session_id=session_id, store=restored_store)

    assert session2.state == State.WAITING_FOR_FOLLOWUP
    assert session2.attempt_count == 1
    assert session2.answers[0].student_answer == "if len(numbers) == 0: return 1"
    assert session2.verdicts[0].is_mismatch is True

    # Complete the flow in Process 2
    step_followup(session2, "if not numbers: return 0")
    assert session2.state == State.CHECKING
    assert session2.attempt_count == 2

    step_checking(session2)
    assert session2.state == State.RECORDED
    assert session2.is_terminated

    # Verify final concept record in DB
    record = restored_store.get_latest_concept_record("recursion_base_case")
    assert record is not None
    assert record.confidence == 3
    assert record.outcome.value == "resolved_on_follow_up"
    assert record.attempts_count == 2
