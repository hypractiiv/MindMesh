"""
concepts/recursion_base_case.py - Domain rules and rubric for the recursion base case concept.

Owns: Question definition, expected pattern rules, follow-up prompts, and benchmark test cases.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple
from models import Question, Verdict


CONCEPT_ID = "recursion_base_case"
CONCEPT_TITLE = "Recursion: Base Case in List Summation"

PROMPT_TEXT = (
    "For a recursive function that sums a list of integers `def sum_list(numbers):`, "
    "what is the base case condition and what value should it return?"
)

CODE_CONTEXT = """def sum_list(numbers):
    # Base case goes here
    ...
    return numbers[0] + sum_list(numbers[1:])
"""

FOLLOW_UP_PROMPT = (
    "Think about what `sum_list([])` should return when there are no elements to sum. "
    "Why would returning 1 cause `sum_list([5])` to equal 6 instead of 5? "
    "Please provide the corrected base case condition and return value."
)

QUESTION = Question(
    concept_id=CONCEPT_ID,
    topic_name=CONCEPT_TITLE,
    prompt_text=PROMPT_TEXT,
    code_context=CODE_CONTEXT,
    options={
        "A": "if len(numbers) == 0: return 1  (Multiplicative identity)",
        "B": "if not numbers: return 0  (Additive identity for empty list)",
        "C": "if not numbers: return None  (Terminates recursion with null)",
        "D": "if len(numbers) == 1: return numbers[0]  (Single element check)",
    },
    correct_option="B",
    explanation=(
        "An empty list has no elements, so its sum must be 0 (the additive identity). "
        "Returning 1 produces an off-by-one error (e.g. sum_list([5]) == 6), "
        "and returning None causes a TypeError when added to an integer."
    ),
    follow_up_prompt=FOLLOW_UP_PROMPT,
    rubric_criteria=[
        "Must check for empty list (e.g. len(numbers) == 0 or not numbers).",
        "Must return 0 (the additive identity).",
        "Returning 1 or None is incorrect.",
    ],
    source_url="https://www.geeksforgeeks.org/recursion-practice-questions-for-gate/",
    quiz_source="LeetCode Explore & GeeksforGeeks Recursion Practice",
)


def evaluate_rule_based(student_answer: str, self_rating: int) -> Verdict:
    """
    Deterministic rule-based evaluator for the recursion base case.
    Matches expected patterns: base case condition checks for empty list and returns 0.
    """
    text = student_answer.strip().lower()

    # Rule checks
    mentions_empty = any(
        kw in text for kw in [
            "len(numbers) == 0",
            "len(numbers) <= 0",
            "len(numbers) < 1",
            "len(n) == 0",
            "not numbers",
            "not n",
            "numbers == []",
            "n == []",
            "empty",
            "zero elements",
            "length equal to zero",
            "length is 0",
            "length 0",
            "no elements",
        ]
    )

    # Check return value
    returns_zero = bool(
        re.search(r"\breturn\s+0\b", text)
        or re.search(r"\bvalue\s*(?:is|should be|must be|to be)?\s*0\b", text)
        or re.search(r"\breturns\s+0\b", text)
        or "additive identity" in text
    )

    returns_one = bool(
        re.search(r"\breturn\s+1\b", text)
        or re.search(r"\bvalue\s*(?:is|should be|must be|to be)?\s*1\b", text)
        or re.search(r"\breturns\s+1\b", text)
    )

    returns_none = bool(re.search(r"\breturn\s+none\b", text) or "returns none" in text)
    returns_list = bool(re.search(r"\breturn\s+\[\s*\]", text) or "return empty list" in text)

    # Evaluate correctness
    if returns_one:
        passed = False
        objection = "Returning 1 introduces an off-by-one error because 1 is the identity for multiplication, not addition."
        reasoning = "Student specified return 1 for empty list, which is the multiplicative identity rather than additive identity."
    elif returns_none:
        passed = False
        objection = "Returning None causes an immediate TypeError when attempting to add it to a list element."
        reasoning = "Student specified returning None."
    elif returns_list:
        passed = False
        objection = "Returning an empty list [] produces a TypeError when combined with integer addition."
        reasoning = "Student specified returning an empty list."
    elif mentions_empty and returns_zero:
        passed = True
        objection = None
        reasoning = "Correctly identified empty list condition and returning 0."
    elif "len(numbers) == 1" in text or "length 1" in text:
        passed = False
        objection = "Using a length-1 base case causes a crash or missing case when an empty list `sum_list([])` is provided."
        reasoning = "Missing empty-list base case."
    elif returns_zero:
        # returns 0 without clear empty check or partially formed
        passed = True
        objection = None
        reasoning = "Identified returning 0 for base case."
    else:
        passed = False
        objection = "The base condition or return value fails to correctly terminate empty-list recursion."
        reasoning = "Did not clearly specify empty list condition or return 0."

    # Mismatch check: student is confident (rating >= 4) but answer is incorrect
    is_mismatch = (not passed) and (self_rating >= 4)

    return Verdict(
        passed=passed,
        objection=objection,
        reasoning=reasoning,
        is_mismatch=is_mismatch,
    )


# 10 Benchmark test answers required by Person 3 specification
BENCHMARK_TEST_ANSWERS: List[Tuple[str, int, bool, str]] = [
    # (student_answer, self_rating, expected_passed, label)
    # 5 Correct-but-oddly-phrased
    ("if not numbers: return 0", 5, True, "correct_standard_pythonic"),
    ("when the list has length equal to zero, return 0", 4, True, "correct_english_phrased"),
    ("base condition is len(numbers) == 0 and the returned value has to be 0 because 0 is the additive identity", 5, True, "correct_conceptual_math"),
    ("if numbers == []: return 0", 3, True, "correct_literal_comparison"),
    ("if len(numbers) < 1: return 0  # handles empty list safely", 4, True, "correct_inequality_with_comment"),

    # 5 Genuinely wrong
    ("if len(numbers) == 0: return 1", 4, False, "wrong_deliberate_demo_case_returns_1"),
    ("return 1 when numbers is empty", 5, False, "wrong_returns_1_natural_language"),
    ("if not numbers: return None", 4, False, "wrong_returns_none_type_error"),
    ("if len(numbers) == 1: return numbers[0]", 5, False, "wrong_length_1_fails_on_empty"),
    ("return [] when empty", 4, False, "wrong_returns_empty_list"),
]
