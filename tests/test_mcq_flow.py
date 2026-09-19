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


def test_mcq_wrong_option_corrected_with_option_letter_no_explanation(temp_store):
    """
    When an answer is wrong on attempt 1, the student enters follow-up.
    In follow-up, there is no need for text explanation:
    Submitting the corrected option letter 'B' directly resolves the question.
    """
    session = FlowSession(store=temp_store, user_id="student_no_exp_needed")
    step_prompting(session, topic="recursion_base_case")

    # Attempt 1: Picks distractor Option C with high confidence
    step_answering(session, "C", self_rating=4)
    step_checking(session)
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Attempt 2: Picks correct Option B with NO text explanation
    step_followup(session, "B")
    step_checking(session)

    assert session.state == State.RECORDED
    record = temp_store.get_latest_concept_record("recursion_base_case", user_id="student_no_exp_needed")
    assert record is not None
    assert record.outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert record.confidence == 3
    assert "Resolved misconception on follow-up" in record.notes


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
    assert q.correct_option in {"A", "B", "C", "D"}
    assert q.explanation is not None
    assert q.quiz_source is not None


def test_curated_topics_have_authentic_quiz_sources():
    """All curated questions must reference authentic quiz websites like GeeksforGeeks, Sanfoundry, LeetCode, etc."""
    recognized_platforms = ["GeeksforGeeks", "Sanfoundry", "LeetCode", "Real Python", "W3Schools", "MDN"]
    assert len(CURATED_TOPICS) >= 15

    for key, q in CURATED_TOPICS.items():
        assert q.quiz_source is not None, f"Topic {key} missing quiz_source"
        assert any(plat in q.quiz_source for plat in recognized_platforms), (
            f"Topic {key} quiz_source '{q.quiz_source}' must reference a recognized platform ({recognized_platforms})"
        )
        assert q.source_url is not None, f"Topic {key} missing source_url"


def test_quicksort_quiz_mcq_flow(temp_store):
    """Test full MCQ follow-up loop on the new QuickSort quiz question."""
    session = FlowSession(store=temp_store, user_id="student_quicksort")
    step_prompting(session, topic="quicksort_pivot_complexity")

    assert "GeeksforGeeks" in session.question.quiz_source
    assert session.question.correct_option == "B"

    # Attempt 1: Wrong option A with high confidence
    step_answering(session, "A", self_rating=5)
    step_checking(session)
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Attempt 2: Selects corrected option B
    step_followup(session, "B")
    step_checking(session)

    assert session.state == State.RECORDED
    rec = temp_store.get_latest_concept_record("quicksort_pivot_complexity", user_id="student_quicksort")
    assert rec is not None
    assert rec.outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert rec.confidence == 3


def test_os_deadlock_quiz_first_try_correct_explanation(temp_store):
    """Test Deadlock quiz question with correct first attempt and verified explanation."""
    session = FlowSession(store=temp_store, user_id="student_os")
    step_prompting(session, topic="os_deadlock_conditions")

    assert "Sanfoundry" in session.question.quiz_source or "GeeksforGeeks" in session.question.quiz_source

    # Attempt 1: Picks correct option B (Preemption is not a deadlock condition)
    step_answering(session, "B", self_rating=5)
    step_checking(session)
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Attempt 2: Submits sound explanation
    step_followup(
        session,
        "The necessary Coffman condition is No Preemption. Preemptive resource allocation is actually a "
        "deadlock recovery technique used by operating systems to break deadlocks."
    )
    step_checking(session)

    assert session.state == State.RECORDED
    rec = temp_store.get_latest_concept_record("os_deadlock_conditions", user_id="student_os")
    assert rec is not None
    assert rec.outcome == Outcome.FIRST_TRY_CORRECT
    assert rec.confidence == 5


def test_shuffle_options_distribution_and_invariants():
    """Verify that Question.shuffle_options() distributes correct answers randomly across A, B, C, and D."""
    from fetcher import CURATED_TOPICS
    base_q = CURATED_TOPICS["recursion_base_case"]
    original_correct_text = base_q.options[base_q.correct_option]

    observed_positions = set()
    for seed in range(50):
        shuffled = base_q.shuffle_options(seed=seed)
        assert set(shuffled.options.keys()) == {"A", "B", "C", "D"}
        assert shuffled.correct_option in {"A", "B", "C", "D"}
        # Guarantee invariant: text of correct answer matches
        assert shuffled.options[shuffled.correct_option] == original_correct_text
        observed_positions.add(shuffled.correct_option)

    # Over 50 shuffles, all 4 positions A, B, C, D must be represented
    assert observed_positions == {"A", "B", "C", "D"}


def test_curated_topics_baseline_not_always_b():
    """Verify that curated topics catalog has a varied distribution of baseline correct options."""
    from fetcher import CURATED_TOPICS
    all_correct_options = {q.correct_option for q in CURATED_TOPICS.values()}
    # Must include A, B, C, and D across the catalog
    assert all_correct_options == {"A", "B", "C", "D"}


def test_provider_get_question_shuffle_enabled():
    """Verify InternetQAProvider.get_question with shuffle=True produces randomized option positions."""
    from fetcher import InternetQAProvider
    provider = InternetQAProvider()
    positions = set()
    for _ in range(30):
        q = provider.get_question("recursion_base_case", shuffle=True)
        positions.add(q.correct_option)
    assert len(positions) > 1


