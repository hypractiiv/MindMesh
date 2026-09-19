"""
tests/test_limits.py - Verification of spend limits and revision limits.

Verifies:
- Hard circuit breaker: Maximum 4 model calls per concept-session.
- Revision limit: Maximum 1 follow-up round based on stored answer records.
"""

import tempfile
from pathlib import Path
import pytest

from flow import FlowSession
from llm import LLMEvaluator, SpendLimitExceededError
from models import Answer, State, Verdict
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_limits.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_spend_limit_max_four_calls():
    """Verify that attempting a 5th model call in the same session raises SpendLimitExceededError."""
    evaluator = LLMEvaluator(mode="fake")
    session_id = "session-spend-limit-1"
    answer = Answer(student_answer="if len(numbers) == 0: return 0", self_rating=5, attempt_number=1)

    # 4 calls are allowed
    for i in range(4):
        evaluator.evaluate(answer, session_id=session_id)

    assert evaluator.get_session_call_count(session_id) == 4

    # 5th call must be blocked
    with pytest.raises(SpendLimitExceededError):
        evaluator.evaluate(answer, session_id=session_id)


def test_revision_limit_max_one_followup_round(temp_store):
    """
    Verify that even if the student's second answer is also wrong and has high confidence,
    the system does NOT loop back to WAITING_FOR_FOLLOWUP. It terminates at RECORDED.
    """
    session = FlowSession(store=temp_store)
    step_prompting(session)

    # Attempt 1: wrong answer + rating 5
    step_answering(session, "if not numbers: return 1", self_rating=5)
    step_checking(session)
    assert session.state == State.WAITING_FOR_FOLLOWUP
    assert session.attempt_count == 1

    # Attempt 2: still wrong answer + rating 5
    step_followup(session, "if not numbers: return 99", self_rating=5)
    assert session.state == State.CHECKING
    assert session.attempt_count == 2

    # Checking exit must resolve to RECORDED (revision limit exhausted)
    step_checking(session)
    assert session.state == State.RECORDED
    assert session.is_terminated

    # Check database: record saved as unresolved
    record = temp_store.get_latest_concept_record("recursion_base_case")
    assert record is not None
    assert record.outcome.value == "unresolved"
    assert record.attempts_count == 2
