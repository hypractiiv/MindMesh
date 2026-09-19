"""
tests/test_flow_reachability.py - Phase 1 cut-line reachability and transition tests.

Verifies:
1. Every state is reachable.
2. The loop stops correctly at terminal states (RECORDED, SKIPPED).
3. Follow-up loop: Mismatch -> Waiting for follow-up -> Checking -> Recorded.
4. Skip/Timeout paths from Answering and Waiting for follow-up.
5. Strict single follow-up limit.
6. Process interruption and resumption from SQLite events.
"""

import tempfile
from pathlib import Path
import pytest

from models import Answer, Question, State, Verdict
from store import MindMeshStore
from flow import FlowSession, InvalidStateTransition


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mindmesh.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_core_loop_reachability(temp_store):
    """Test standard correct path: Prompting -> Answering -> Checking -> Recorded."""
    session = FlowSession(store=temp_store)
    assert session.state == State.PROMPTING

    # Prompting -> Answering
    session.transition_to(State.ANSWERING, "QUESTION_LOADED", {"concept": "recursion_base_case"})
    assert session.state == State.ANSWERING

    # Answering -> Checking
    answer = Answer(student_answer="def sum_list(n): return 0 if not n else n[0] + sum_list(n[1:])", self_rating=5, attempt_number=1)
    session.answers.append(answer)
    session.transition_to(State.CHECKING, "ANSWER_SUBMITTED", {"answer": answer.model_dump()})
    assert session.state == State.CHECKING

    # Evaluator passes
    verdict = Verdict(passed=True, reasoning="Correct base case")
    next_state = session.determine_checking_exit(verdict)
    assert next_state == State.RECORDED

    session.transition_to(State.RECORDED, "RECORD_SAVED", {"verdict": verdict.model_dump()})
    assert session.state == State.RECORDED
    assert session.is_terminated


def test_mismatch_followup_loop_reachability(temp_store):
    """
    Test mismatch path:
    Prompting -> Answering -> Checking -> Waiting for follow-up -> Checking -> Recorded
    """
    session = FlowSession(store=temp_store)

    # 1. Prompting -> Answering
    session.transition_to(State.ANSWERING, "QUESTION_LOADED")

    # 2. Student gives wrong answer with high confidence (4/5)
    wrong_answer = Answer(student_answer="if len(n) == 0: return 1", self_rating=4, attempt_number=1)
    session.answers.append(wrong_answer)
    session.transition_to(State.CHECKING, "ANSWER_SUBMITTED", {"answer": wrong_answer.model_dump()})

    # Evaluator detects wrong answer + mismatch
    verdict1 = Verdict(passed=False, objection="Empty list sum must return 0, not 1", is_mismatch=True)
    next_state = session.determine_checking_exit(verdict1)
    assert next_state == State.WAITING_FOR_FOLLOWUP

    # 3. Checking -> Waiting for follow-up (adaptive backward transition)
    session.transition_to(
        State.WAITING_FOR_FOLLOWUP,
        "FOLLOWUP_REQUESTED",
        {"objection": verdict1.objection, "question": "Why would returning 1 cause sum_list([5]) to equal 6?"}
    )
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # 4. Student submits corrected answer
    corrected_answer = Answer(student_answer="if not n: return 0", self_rating=4, attempt_number=2)
    session.answers.append(corrected_answer)
    session.transition_to(State.CHECKING, "FOLLOWUP_SUBMITTED", {"answer": corrected_answer.model_dump()})
    assert session.state == State.CHECKING

    # 5. Evaluator passes corrected answer
    verdict2 = Verdict(passed=True, reasoning="Base case now returns 0")
    next_state = session.determine_checking_exit(verdict2)
    assert next_state == State.RECORDED

    session.transition_to(State.RECORDED, "RECORD_SAVED", {"verdict": verdict2.model_dump()})
    assert session.state == State.RECORDED
    assert session.is_terminated


def test_single_followup_limit(temp_store):
    """
    Verifies that if the follow-up answer is still wrong, the system
    does NOT enter an infinite loop; it terminates at Recorded because attempt_count == 2.
    """
    session = FlowSession(store=temp_store)
    session.transition_to(State.ANSWERING, "QUESTION_LOADED")

    # Attempt 1 (wrong + rating 5)
    session.answers.append(Answer(student_answer="return 1", self_rating=5, attempt_number=1))
    session.transition_to(State.CHECKING, "ANSWER_SUBMITTED")

    v1 = Verdict(passed=False, is_mismatch=True)
    assert session.determine_checking_exit(v1) == State.WAITING_FOR_FOLLOWUP
    session.transition_to(State.WAITING_FOR_FOLLOWUP, "FOLLOWUP_REQUESTED")

    # Attempt 2 (still wrong + rating 5)
    session.answers.append(Answer(student_answer="return -1", self_rating=5, attempt_number=2))
    session.transition_to(State.CHECKING, "FOLLOWUP_SUBMITTED")

    v2 = Verdict(passed=False, is_mismatch=True)
    # Since attempt_count is now 2, max 1 follow-up round is enforced!
    assert session.determine_checking_exit(v2) == State.RECORDED


def test_skip_paths_reachability(temp_store):
    """Test skipped/timeout paths from Answering and Waiting for follow-up."""
    # From Answering -> Skipped
    s1 = FlowSession(store=temp_store)
    s1.transition_to(State.ANSWERING, "QUESTION_LOADED")
    s1.transition_to(State.SKIPPED, "SESSION_SKIPPED", {"reason": "timeout"})
    assert s1.state == State.SKIPPED
    assert s1.is_terminated

    # From Waiting for follow-up -> Skipped
    s2 = FlowSession(store=temp_store)
    s2.transition_to(State.ANSWERING, "QUESTION_LOADED")
    s2.answers.append(Answer(student_answer="wrong", self_rating=4, attempt_number=1))
    s2.transition_to(State.CHECKING, "ANSWER_SUBMITTED")
    s2.transition_to(State.WAITING_FOR_FOLLOWUP, "FOLLOWUP_REQUESTED")
    s2.transition_to(State.SKIPPED, "SESSION_SKIPPED", {"reason": "user_cancelled"})
    assert s2.state == State.SKIPPED
    assert s2.is_terminated


def test_invalid_transitions_rejected(temp_store):
    """Test illegal transitions raise InvalidStateTransition."""
    session = FlowSession(store=temp_store)
    with pytest.raises(InvalidStateTransition):
        # Cannot jump straight from Prompting to Checking
        session.transition_to(State.CHECKING, "ILLEGAL")

    session.transition_to(State.ANSWERING, "QUESTION_LOADED")
    with pytest.raises(InvalidStateTransition):
        # Cannot jump from Answering to Waiting for follow-up
        session.transition_to(State.WAITING_FOR_FOLLOWUP, "ILLEGAL")


def test_session_recovery_after_interruption(temp_store):
    """Simulate a killed process during Waiting for follow-up and recover seamlessly."""
    session_id = "test-resumable-session-123"
    s = FlowSession(session_id=session_id, store=temp_store)

    q = Question(
        concept_id="recursion_base_case",
        prompt_text="What is the base case condition and return value?",
    )
    s.question = q
    s.transition_to(State.ANSWERING, "QUESTION_LOADED", {"question": q.model_dump()})

    ans = Answer(student_answer="return 1", self_rating=4, attempt_number=1)
    s.answers.append(ans)
    s.transition_to(State.CHECKING, "ANSWER_SUBMITTED", {"answer": ans.model_dump()})

    verd = Verdict(passed=False, objection="Sum of empty list must be 0", is_mismatch=True)
    s.verdicts.append(verd)
    s.transition_to(State.WAITING_FOR_FOLLOWUP, "FOLLOWUP_REQUESTED", {"verdict": verd.model_dump()})

    # "Simulate crash" - create a new FlowSession by resuming from database
    resumed_session = FlowSession.resume(session_id=session_id, store=temp_store)
    assert resumed_session.state == State.WAITING_FOR_FOLLOWUP
    assert resumed_session.attempt_count == 1
    assert resumed_session.question.concept_id == "recursion_base_case"
    assert len(resumed_session.answers) == 1
    assert resumed_session.answers[0].student_answer == "return 1"
    assert resumed_session.verdicts[0].is_mismatch is True

    # Continue session to completion
    ans2 = Answer(student_answer="return 0", self_rating=4, attempt_number=2)
    resumed_session.answers.append(ans2)
    resumed_session.transition_to(State.CHECKING, "FOLLOWUP_SUBMITTED", {"answer": ans2.model_dump()})
    assert resumed_session.state == State.CHECKING
