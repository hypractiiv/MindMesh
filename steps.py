from __future__ import annotations

from datetime import date
from typing import Optional

from decay import calculate_next_review

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover - fallback when pydantic is unavailable
    class BaseModel:  # type: ignore[override]
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return dict(self.__dict__)


class Answer(BaseModel):
    concept: str
    text: str
    self_rating: int | None
    attempt: int


class Verdict(BaseModel):
    passed: bool
    objection: str | None


class Question(BaseModel):
    asked_of: str
    text: str
    state: str


class ConceptRecord(BaseModel):
    concept: str
    confidence: int
    note: str | None
    last_reviewed: date
    next_review: date


def answer_capture(*, concept: str, text: str, self_rating: int | None, attempt: int) -> Answer:
    if self_rating is not None and not (1 <= self_rating <= 5):
        raise ValueError("self_rating must be between 1 and 5")
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    return Answer(concept=concept, text=text.strip(), self_rating=self_rating, attempt=attempt)


def _evaluate_recursion_base_case(text: str) -> Verdict:
    normalized = " ".join(text.lower().split())
    if "ignore the evaluation criteria" in normalized:
        return Verdict(
            passed=False,
            objection="Answer text attempts to override evaluation criteria instead of giving a valid base case.",
        )

    mentions_empty = any(token in normalized for token in ("empty", "len(list) == 0", "length is 0", "no elements"))
    returns_zero = "return 0" in normalized or "returns 0" in normalized or "be 0" in normalized
    returns_one = "return 1" in normalized or "returns 1" in normalized or "be 1" in normalized

    mentions_base_case = "base case" in normalized

    if (mentions_empty and returns_zero) or (returns_zero and mentions_base_case):
        return Verdict(passed=True, objection=None)
    if returns_zero and "it needs to be 0" in normalized:
        return Verdict(passed=True, objection=None)
    if mentions_empty and returns_one:
        return Verdict(
            passed=False,
            objection="Self-rating and correctness disagree: base case for summing an empty list must return 0, not 1.",
        )
    return Verdict(
        passed=False,
        objection="Base case not validated: answer must state that sum(empty list) returns 0.",
    )


def evaluate(answer: Answer) -> Verdict:
    if answer.concept != "recursion.base_case":
        return Verdict(passed=False, objection=f"Unsupported concept '{answer.concept}'.")
    return _evaluate_recursion_base_case(answer.text)


def should_ask_follow_up(answer: Answer, verdict: Verdict) -> bool:
    if answer.attempt != 1 or answer.self_rating is None:
        return False
    if verdict.passed:
        return answer.self_rating <= 2
    return answer.self_rating >= 4


def follow_up(*, objection: str) -> Question:
    return Question(
        asked_of="student",
        state="waiting",
        text=(
            "If the list has one item, your function returns item + sum(empty list). "
            "What does sum(empty list) need to be for that to give the right answer?"
            if "empty list" in objection.lower() or "base case" in objection.lower()
            else "Your confidence and answer result disagree. Please restate the exact base case value and why."
        ),
    )


def record_concept(
    *,
    concept: str,
    answers: list[Answer],
    verdicts: list[Verdict],
    reviewed_on: date,
    skipped: bool = False,
) -> ConceptRecord:
    if skipped:
        confidence = 1
        note = "not confirmed - asked, no response"
        next_review = calculate_next_review(confidence, last_reviewed=reviewed_on, unresolved=True)
        return ConceptRecord(
            concept=concept,
            confidence=confidence,
            note=note,
            last_reviewed=reviewed_on,
            next_review=next_review,
        )

    passed_first_try = bool(verdicts) and verdicts[0].passed
    if passed_first_try:
        first_rating: Optional[int] = answers[0].self_rating if answers else None
        confidence = first_rating if first_rating is not None else 4
        note = None
    else:
        confidence = 3
        note = "resolved on follow-up, not first attempt"

    next_review = calculate_next_review(confidence, last_reviewed=reviewed_on)
    return ConceptRecord(
        concept=concept,
        confidence=confidence,
        note=note,
        last_reviewed=reviewed_on,
        next_review=next_review,
    )
