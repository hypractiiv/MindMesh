"""
tests/test_mcq_flow.py - Tests for Multiple Choice Question (MCQ) and First-Try Explanation Verification.

Verifies:
1. Right answer on first try prompts for explanation to prevent lucky guessing.
2. Verified explanation confirms FIRST_TRY_CORRECT with high confidence.
3. Lucky guess without explanation fails into UNRESOLVED with low confidence.
4. Wrong MCQ option with high confidence triggers mismatch objection and follow-up.
5. All curated catalog topics provide 4 distinct options (A, B, C, D) and reference explanations.
6. Live internet fetcher synthesizes 4 distinct MCQ options.
"""

import tempfile
from pathlib import Path
import pytest

from fetcher import CURATED_TOPICS, InternetQAProvider
from flow import FlowSession
from models import Outcome, State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mcq.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_mcq_first_try_correct_asks_explanation(temp_store):
    """
    When the student picks the correct option on attempt 1:
    - Session MUST transition to WAITING_FOR_FOLLOWUP to request an explanation.
    - Submitting a sound explanation transitions to RECORDED with FIRST_TRY_CORRECT.
    """
    session = FlowSession(store=temp_store, user_id="student_1")
    step_prompting(session, topic="recursion_base_case")

    assert session.question.options is not None
    assert "B" in session.question.options
    assert session.question.correct_option == "B"

    # Step 1: Student selects correct Option B with 5/5 confidence
    step_answering(session, "B", self_rating=5)
    step_checking(session)

    # Must ask for explanation, NOT immediately terminate!
    assert session.state == State.WAITING_FOR_FOLLOWUP
    assert session.attempt_count == 1

    # Verify event audit trail
    events = temp_store.get_session_events(session.session_id)
    assert events[-1].event_type == "EXPLANATION_REQUESTED"
    assert "guessed" in events[-1].payload["follow_up_prompt"].lower()

    # Step 2: Student provides sound explanation
    step_followup(
        session,
        "An empty list has zero elements, so the recursive sum must return 0 as the additive identity. "
        "Returning 1 would cause an off-by-one sum, and returning None causes a TypeError.",
    )
    assert session.state == State.CHECKING
    assert session.attempt_count == 2

    # Step 3: Explanation verified and recorded
    step_checking(session)
    assert session.state == State.RECORDED
    assert session.is_terminated

    record = temp_store.get_latest_concept_record("recursion_base_case", user_id="student_1")
    assert record is not None
    assert record.outcome == Outcome.FIRST_TRY_CORRECT
    assert record.confidence == 5
    assert "Verified understanding" in record.notes


def test_mcq_lucky_guess_fails_explanation(temp_store):
    """
    If the student selects the correct MCQ option but admits they guessed,
    the explanation fails and the outcome is recorded as UNRESOLVED with degraded confidence.
    """
    session = FlowSession(store=temp_store, user_id="student_guesser")
    step_prompting(session, topic="recursion_base_case")

    # Step 1: Lucky guess on Option B with confidence 4
    step_answering(session, "B", self_rating=4)
    step_checking(session)
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Step 2: Student admits to guessing
    step_followup(session, "I don't know, I just guessed B randomly.")
    step_checking(session)

    assert session.state == State.RECORDED
    record = temp_store.get_latest_concept_record("recursion_base_case", user_id="student_guesser")
    assert record is not None
    assert record.outcome == Outcome.UNRESOLVED
    assert record.confidence <= 2
    assert "explanation was unconvincing" in record.notes.lower()


def test_mcq_wrong_option_mismatch(temp_store):
    """
    Selecting a wrong distractor option with high confidence (>=4)
    triggers a mismatch objection and routes to WAITING_FOR_FOLLOWUP.
    """
    session = FlowSession(store=temp_store, user_id="student_mismatch")
    step_prompting(session, topic="recursion_base_case")

    # Distractor Option A (multiplicative identity 1) with confidence 5
    step_answering(session, "A", self_rating=5)
    step_checking(session)

    assert session.state == State.WAITING_FOR_FOLLOWUP
    events = temp_store.get_session_events(session.session_id)
    assert events[-1].event_type == "FOLLOWUP_REQUESTED"
    assert "Option A is incorrect" in events[-1].payload["objection"]

    # Student corrects their answer on follow-up
    step_followup(session, "if not numbers: return 0 (empty list must return 0)")
    step_checking(session)

    assert session.state == State.RECORDED
    record = temp_store.get_latest_concept_record("recursion_base_case", user_id="student_mismatch")
    assert record is not None
    assert record.outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert record.confidence == 3


def test_curated_topics_all_have_four_options():
    """Every topic in the curated catalog must have 4 MCQ options, a correct_option, and an explanation."""
    for key, q in CURATED_TOPICS.items():
        assert q.options is not None, f"Topic {key} missing options"
        assert set(q.options.keys()) == {"A", "B", "C", "D"}, f"Topic {key} must have exactly options A, B, C, D"
        assert q.correct_option in {"A", "B", "C", "D"}, f"Topic {key} invalid correct_option: {q.correct_option}"
        assert q.explanation and len(q.explanation) > 20, f"Topic {key} missing explanation"


def test_live_fetcher_synthesizes_mcq():
    """Dynamic internet fetching synthesizes 4 MCQ options with correct_option and explanation."""
    provider = InternetQAProvider()
    q = provider.fetch_from_internet("Hash Table Collision Resolution")

    assert q.options is not None
    assert len(q.options) == 4
    assert set(q.options.keys()) == {"A", "B", "C", "D"}
    assert q.correct_option == "B"
    assert q.explanation is not None
