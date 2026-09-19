"""
tests/test_gemini_qa.py - Verification of dynamic Q&A generation via Google Gemini API.

Verifies:
1. InternetQAProvider connects to Gemini API using GEMINI_API_KEY.
2. Dynamic synthesis creates a structured Question with authentic 4 MCQ options,
   explanation, rubric, and quiz source citation.
3. FlowSession works end-to-end with the Gemini-generated question.
4. Resilient fallback occurs if Gemini API key is missing or offline.
"""

import tempfile
from pathlib import Path
import pytest

from fetcher import InternetQAProvider
from flow import FlowSession
from models import Outcome, Question, State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_gemini.db"
        yield MindMeshStore(db_path=db_path)


def test_gemini_fetch_synthesizes_authentic_mcq():
    """Verify Gemini API synthesizes a valid Question model with authentic options and quiz source."""
    provider = InternetQAProvider()
    if not provider.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not configured")

    q = provider.fetch_with_gemini("Red-Black Tree Self Balancing")
    if q is None:
        pytest.skip("Gemini API call returned None (e.g. rate limit / network)")

    assert isinstance(q, Question)
    assert q.concept_id is not None
    assert q.topic_name is not None
    assert len(q.prompt_text) > 20
    assert q.options is not None
    assert set(q.options.keys()) == {"A", "B", "C", "D"}
    assert q.correct_option in {"A", "B", "C", "D"}
    assert q.explanation is not None and len(q.explanation) >= 20
    assert q.quiz_source is not None and "Gemini" in q.quiz_source
    assert q.source_url is not None


def test_gemini_question_flow_session(temp_store):
    """Verify that a Gemini-synthesized question can run through the full stateful flow loop."""
    provider = InternetQAProvider()
    if not provider.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not configured")

    q = provider.fetch_with_gemini("Trie Prefix Search")
    if q is None:
        pytest.skip("Gemini API unavailable")

    session = FlowSession(store=temp_store, user_id="student_gemini_test")
    step_prompting(session, question=q)

    assert session.state == State.ANSWERING
    assert session.question.concept_id == q.concept_id

    # Attempt 1: Pick correct option
    correct_opt = q.correct_option or "B"
    step_answering(session, correct_opt, self_rating=5)
    step_checking(session)

    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Attempt 2: Sound explanation
    step_followup(
        session,
        "A Trie shares prefixes across keys, allowing O(L) time complexity where L is the key length."
    )
    step_checking(session)

    assert session.state == State.RECORDED
    record = temp_store.get_latest_concept_record(q.concept_id, user_id="student_gemini_test")
    assert record is not None
    assert record.outcome == Outcome.FIRST_TRY_CORRECT


def test_gemini_offline_fallback():
    """Verify that when no Gemini API key is provided, fetch_from_internet cleanly falls back to deterministic/wiki."""
    provider = InternetQAProvider(api_key=None)
    provider.gemini_api_key = None

    q = provider.fetch_from_internet("Dijkstra Shortest Path", use_gemini=False)
    assert isinstance(q, Question)
    assert q.options is not None
    assert set(q.options.keys()) == {"A", "B", "C", "D"}
    assert q.correct_option == "B"
    assert q.explanation is not None
