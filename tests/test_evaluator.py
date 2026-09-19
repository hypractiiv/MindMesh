"""
tests/test_evaluator.py - Verification of 10 benchmark evaluator test answers.

Verifies:
- 5 correct-but-oddly-phrased answers pass.
- 5 genuinely wrong answers fail with clear objections.
- Evaluator produces machine-readable Verdict models.
- Logs misclassifications if any exist.
"""

import pytest
from concepts.recursion_base_case import BENCHMARK_TEST_ANSWERS
from llm import LLMEvaluator
from models import Answer


@pytest.mark.parametrize("student_answer,self_rating,expected_passed,label", BENCHMARK_TEST_ANSWERS)
def test_benchmark_evaluator_cases(student_answer, self_rating, expected_passed, label):
    """Test all 10 benchmark answers against the evaluator."""
    evaluator = LLMEvaluator(mode="fake")
    answer = Answer(
        student_answer=student_answer,
        self_rating=self_rating,
        attempt_number=1,
    )

    verdict = evaluator.evaluate(answer, session_id="eval-benchmark-session")

    # Assert correctness
    assert verdict.passed == expected_passed, (
        f"Benchmark '{label}' misclassified! "
        f"Expected passed={expected_passed}, got passed={verdict.passed}. "
        f"Reasoning: {verdict.reasoning}"
    )

    if not expected_passed:
        assert verdict.objection is not None, f"Expected objection for wrong answer in '{label}'"
        if self_rating >= 4:
            assert verdict.is_mismatch is True, f"Expected is_mismatch=True for high confidence wrong answer in '{label}'"
    else:
        assert verdict.objection is None
