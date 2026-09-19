"""
tests/test_internet_fetcher.py - Verification of internet Q&A provider and dynamic topic evaluation.

Verifies:
- Curated catalog topic retrieval.
- Live internet fetching and question synthesis.
- Dynamic evaluation with topic rubrics and mismatch detection.
- Multi-topic persistent isolation in SQLite.
"""

import tempfile
from pathlib import Path
import pytest

from fetcher import CURATED_TOPICS, InternetQAProvider
from flow import FlowSession
from models import State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_multi_topic.db"
        yield MindMeshStore(db_path=db_path)


def test_curated_catalog_topics():
    """Verify all curated topics exist and have complete rubric and follow-up data."""
    provider = InternetQAProvider()
    topics = provider.list_curated_topics()
    assert len(topics) >= 5

    # Check Binary Search
    bs_q = provider.get_question("binary_search_bounds")
    assert bs_q.concept_id == "binary_search_bounds"
    assert bs_q.source_url is not None
    assert len(bs_q.rubric_criteria) >= 2
    assert "low <= high" in bs_q.rubric_criteria[0]

    # Check SQL
    sql_q = provider.get_question("sql_where_vs_having")
    assert sql_q.concept_id == "sql_where_vs_having"
    assert "WHERE" in sql_q.prompt_text
    assert "HAVING" in sql_q.prompt_text


def test_live_internet_fetch_fallback():
    """Verify live internet fetch creates a valid Question object even for arbitrary topics."""
    provider = InternetQAProvider()
    q = provider.get_question("Dijkstra's algorithm")

    assert q.concept_id == "dijkstra_s_algorithm"
    assert q.topic_name is not None
    assert "Dijkstra" in q.prompt_text
    assert q.follow_up_prompt is not None
    assert len(q.rubric_criteria) >= 2
    assert q.source_url.startswith("https://en.wikipedia.org/")


def test_binary_search_mismatch_and_recovery(temp_store):
    """
    Test dynamic agentic loop on an internet topic (Binary Search):
    1. Student answers with `<` instead of `<=`, rating 4/5 (mismatch!).
    2. System catches mismatch and asks targeted follow-up.
    3. Student corrects to `while low <= high`.
    4. Evaluator passes and records completion.
    """
    session = FlowSession(store=temp_store)
    step_prompting(session, topic="binary_search_bounds")
    assert session.question.concept_id == "binary_search_bounds"

    # Confident wrong answer (missing = in loop bound)
    step_answering(session, "while low < high: mid = (low + high) // 2", self_rating=4)
    verd1 = step_checking(session)

    assert verd1.passed is False
    assert verd1.is_mismatch is True
    assert session.state == State.WAITING_FOR_FOLLOWUP

    # Corrected follow-up
    step_followup(session, "while low <= high: mid = low + (high - low) // 2")
    verd2 = step_checking(session)

    assert verd2.passed is True
    assert session.state == State.RECORDED

    # Verify SQLite record saved specifically for binary_search_bounds
    rec = temp_store.get_latest_concept_record("binary_search_bounds")
    assert rec is not None
    assert rec.concept_id == "binary_search_bounds"
    assert rec.confidence == 3
    assert rec.outcome.value == "resolved_on_follow_up"


def test_multi_topic_persistence_isolation(temp_store):
    """Verify that multiple different topics persist independently in SQLite."""
    # Session 1: Recursion
    # Session 1: Recursion
    s1 = FlowSession(session_id="multi-sess-1", store=temp_store)
    step_prompting(s1, topic="recursion_base_case")
    step_answering(s1, "B", self_rating=5)
    step_checking(s1)
    step_followup(s1, "Empty list has 0 elements so returns 0 as additive identity.")
    step_checking(s1)

    # Session 2: SQL
    s2 = FlowSession(session_id="multi-sess-2", store=temp_store)
    step_prompting(s2, topic="sql_where_vs_having")
    step_answering(s2, "B", self_rating=5)
    step_checking(s2)
    step_followup(s2, "WHERE filters rows before GROUP BY; HAVING filters aggregate groups after.")
    step_checking(s2)

    # Query by concept
    rec_rec = temp_store.get_latest_concept_record("recursion_base_case")
    rec_sql = temp_store.get_latest_concept_record("sql_where_vs_having")

    assert rec_rec is not None
    assert rec_rec.concept_id == "recursion_base_case"

    assert rec_sql is not None
    assert rec_sql.concept_id == "sql_where_vs_having"
    assert rec_sql.session_id == "multi-sess-2"

    # Both concepts are tracked in SQLite
    all_events = temp_store.get_all_session_events()
    assert len(all_events) >= 6
