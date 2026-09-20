"""
tests/test_openai_gemini_fallback.py - Comprehensive verification of OpenAI primary and Gemini fallback architecture.

Verifies:
1. LLMEvaluator dispatches to OpenAI when configured.
2. LLMEvaluator transparently falls back to Gemini when OpenAI encounters an error.
3. LLMEvaluator falls back to deterministic rule engine when both OpenAI and Gemini fail.
4. InternetQAProvider prioritizes OpenAI for question synthesis.
5. InternetQAProvider transparently falls back to Gemini when OpenAI is unavailable or fails.
6. Question metadata accurately stamps source_provider, is_fallback, and fallback_chain.
"""

from unittest.mock import MagicMock, patch
import pytest

from fetcher import InternetQAProvider
from llm import LLMEvaluator
from models import Answer, Question, Verdict


@pytest.fixture
def sample_question():
    return Question(
        concept_id="binary_search_bounds",
        topic_name="Binary Search Bounds",
        prompt_text="What is the loop continuation condition in binary search?",
        options={
            "A": "while low < high",
            "B": "while low <= high",
            "C": "while low != high",
            "D": "while low > high",
        },
        correct_option="B",
        explanation="low <= high is needed to inspect the single-element candidate at the boundary.",
        follow_up_prompt="Explain why low <= high is necessary.",
        rubric_criteria=["Must mention boundary inclusivity low <= high."],
    )


def test_evaluator_dispatches_to_openai_as_primary(sample_question):
    """Verify that when OpenAI is configured, it is called as the primary grader."""
    evaluator = LLMEvaluator(api_key="mock-openai-key", mode="auto")
    answer = Answer(student_answer="Because single element subarrays require low <= high to be checked.", self_rating=5, attempt_number=2)

    with patch.object(
        evaluator,
        "_call_real_model",
        return_value=Verdict(passed=True, reasoning="Evaluated via OpenAI primary")
    ) as mock_openai, patch.object(evaluator, "_call_gemini_model") as mock_gemini:
        verdict = evaluator.evaluate(answer, "sess-openai-1", question=sample_question, is_explanation=True)

        assert verdict.passed is True
        assert "OpenAI primary" in verdict.reasoning
        mock_openai.assert_called_once()
        mock_gemini.assert_not_called()


def test_evaluator_transparent_fallback_to_gemini(sample_question):
    """Verify that when OpenAI fails, evaluation transparently falls back to Gemini."""
    evaluator = LLMEvaluator(api_key="mock-openai-key", gemini_api_key="mock-gemini-key", mode="auto")
    answer = Answer(student_answer="low <= high ensures single elements are inspected", self_rating=5, attempt_number=2)

    with patch.object(
        evaluator,
        "_call_real_model",
        side_effect=RuntimeError("OpenAI API 429 Rate Limit")
    ) as mock_openai, patch.object(
        evaluator,
        "_call_gemini_model",
        return_value=Verdict(passed=True, reasoning="Evaluated via Gemini fallback")
    ) as mock_gemini:
        verdict = evaluator.evaluate(answer, "sess-fallback-gemini", question=sample_question, is_explanation=True)

        assert verdict.passed is True
        assert "Gemini fallback" in verdict.reasoning
        assert "Gemini Fallback: OpenAI" in verdict.reasoning
        mock_openai.assert_called_once()
        mock_gemini.assert_called_once()


def test_evaluator_emergency_fallback_to_rules_when_both_fail(sample_question):
    """Verify that when both OpenAI and Gemini fail, deterministic rule evaluation takes over."""
    evaluator = LLMEvaluator(api_key="mock-openai-key", gemini_api_key="mock-gemini-key", mode="auto")
    answer = Answer(student_answer="low <= high boundary inclusivity and mid calculation", self_rating=4, attempt_number=2)

    with patch.object(
        evaluator,
        "_call_real_model",
        side_effect=RuntimeError("OpenAI connection timed out")
    ), patch.object(
        evaluator,
        "_call_gemini_model",
        side_effect=RuntimeError("Gemini service unavailable 503")
    ):
        verdict = evaluator.evaluate(answer, "sess-fallback-rules", question=sample_question, is_explanation=True)

        assert verdict.passed is True
        assert "Rule Fallback: OpenAI: OpenAI connection timed out; Gemini: Gemini service unavailable 503" in verdict.reasoning


def test_fetcher_prioritizes_openai_synthesis():
    """Verify that fetch_from_internet prioritizes fetch_with_openai."""
    provider = InternetQAProvider(api_key="mock-openai-key", gemini_api_key="mock-gemini-key")

    mock_q = Question(
        concept_id="trie_prefix",
        topic_name="Trie Prefix Search",
        prompt_text="What is the time complexity of a Trie prefix search?",
        options={"A": "O(1)", "B": "O(L)", "C": "O(N)", "D": "O(N log N)"},
        correct_option="B",
        explanation="O(L) where L is prefix length.",
        source_provider="openai",
        is_fallback=False,
    )

    with patch.object(provider, "fetch_with_openai", return_value=mock_q) as mock_openai, \
         patch.object(provider, "fetch_with_gemini") as mock_gemini:
        q = provider.fetch_from_internet("Trie Prefix Search")

        assert q.source_provider == "openai"
        assert q.is_fallback is False
        mock_openai.assert_called_once()
        mock_gemini.assert_not_called()


def test_fetcher_falls_back_to_gemini_when_openai_fails():
    """Verify that fetch_from_internet falls back to Gemini when OpenAI returns None."""
    provider = InternetQAProvider(api_key="mock-openai-key", gemini_api_key="mock-gemini-key")

    gemini_q = Question(
        concept_id="trie_prefix",
        topic_name="Trie Prefix Search",
        prompt_text="What is the time complexity of a Trie prefix search?",
        options={"A": "O(1)", "B": "O(L)", "C": "O(N)", "D": "O(N log N)"},
        correct_option="B",
        explanation="O(L) where L is prefix length.",
        source_provider="gemini",
        is_fallback=False,
    )

    with patch.object(provider, "fetch_with_openai", return_value=None) as mock_openai, \
         patch.object(provider, "fetch_with_gemini", return_value=gemini_q) as mock_gemini:
        q = provider.fetch_from_internet("Trie Prefix Search")

        assert q.source_provider == "gemini"
        assert q.is_fallback is True
        assert q.fallback_chain == ["openai", "gemini"]
        mock_openai.assert_called_once()
        mock_gemini.assert_called_once()


def test_fetcher_offline_fallback_transparent_tagging():
    """Verify that when external AI APIs are disabled or fail, the question is explicitly stamped as fallback."""
    provider = InternetQAProvider()
    provider.openai_api_key = None
    provider.gemini_api_key = None

    q = provider.fetch_from_internet("Dijkstra Shortest Path", use_openai=False, use_gemini=False)

    assert q.is_fallback is True
    assert q.source_provider in ("wikipedia", "offline_fallback")
    assert "Fallback" in (q.quiz_source or "")
