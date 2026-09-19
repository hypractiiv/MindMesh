"""
steps.py - Step implementations for MindMesh.

Owns:
- Step execution for Prompting, Answering, Checking, Waiting for follow-up, Recorded, and Skipped.
- Integration between FlowSession, LLMEvaluator, and MindMeshStore.
"""

from __future__ import annotations

from typing import Optional
from concepts.recursion_base_case import QUESTION as DEFAULT_QUESTION
from decay import calculate_next_review
from fetcher import InternetQAProvider
from flow import FlowSession
from llm import LLMEvaluator, get_evaluator
from models import Answer, ConceptRecord, Outcome, Question, State, Verdict


def step_prompting(
    session: FlowSession,
    topic: Optional[str] = None,
    question: Optional[Question] = None,
) -> None:
    """
    Executes Prompting step:
    Loads target concept question (either specified, fetched from internet, or default),
    checks prior history for second-encounter context, and transitions session to Answering.
    """
    if question is not None:
        session.question = question
    elif topic is not None:
        provider = InternetQAProvider()
        session.question = provider.get_question(topic)
    elif session.question is None:
        session.question = DEFAULT_QUESTION

    active_question = session.question

    # Check for prior encounter history in persistent store for this specific concept and student
    prior_records = session.store.get_concept_records(active_question.concept_id, user_id=session.user_id)
    prior_history_summary = None
    if prior_records:
        latest = prior_records[-1]
        prior_history_summary = {
            "previous_encounters": len(prior_records),
            "last_outcome": latest.outcome.value,
            "last_confidence": latest.confidence,
            "last_reviewed_at": latest.created_at.isoformat(),
        }

    session.transition_to(
        State.ANSWERING,
        "QUESTION_LOADED",
        {
            "question": active_question.model_dump(),
            "prior_history": prior_history_summary,
        },
    )


def step_answering(
    session: FlowSession,
    student_answer: str,
    self_rating: int,
) -> Answer:
    """
    Executes Answering step:
    Captures student's initial answer and self-confidence rating (1-5),
    persists the event, and transitions session to Checking.
    """
    answer = Answer(
        student_answer=student_answer,
        self_rating=self_rating,
        attempt_number=1,
    )
    session.answers.append(answer)

    session.transition_to(
        State.CHECKING,
        "ANSWER_SUBMITTED",
        {"answer": answer.model_dump()},
    )
    return answer


def step_checking(
    session: FlowSession,
    evaluator: Optional[LLMEvaluator] = None,
) -> Verdict:
    """
    Executes Checking step:
    Invokes centralized LLM evaluator with topic rubric to judge student answer.
    Detects confidence/correctness mismatch.
    Routes to WAITING_FOR_FOLLOWUP (on mismatch attempt 1) or RECORDED (on pass or final attempt).
    """
    active_evaluator = evaluator or get_evaluator()
    current_answer = session.answers[-1]

    verdict = active_evaluator.evaluate(
        current_answer,
        session_id=session.session_id,
        question=session.question,
    )
    session.verdicts.append(verdict)

    next_state = session.determine_checking_exit(verdict)

    if next_state == State.WAITING_FOR_FOLLOWUP:
        session.transition_to(
            State.WAITING_FOR_FOLLOWUP,
            "FOLLOWUP_REQUESTED",
            {
                "verdict": verdict.model_dump(),
                "objection": verdict.objection,
                "follow_up_prompt": session.question.follow_up_prompt if session.question else None,
            },
        )
    else:
        # Transitioning to RECORDED
        step_record(session)

    return verdict


def step_followup(
    session: FlowSession,
    follow_up_answer: str,
    self_rating: Optional[int] = None,
) -> Answer:
    """
    Executes Waiting for follow-up exit:
    Student provides a follow-up clarification.
    Transitions back to Checking for second evaluation.
    """
    rating = self_rating or (session.answers[0].self_rating if session.answers else 3)
    answer = Answer(
        student_answer=follow_up_answer,
        self_rating=rating,
        attempt_number=2,
    )
    session.answers.append(answer)

    session.transition_to(
        State.CHECKING,
        "FOLLOWUP_SUBMITTED",
        {"answer": answer.model_dump()},
    )
    return answer


def step_record(session: FlowSession) -> ConceptRecord:
    """
    Executes Recorded step:
    Resolves the final attempt, calculates spaced-repetition next review date,
    stores ConceptRecord in SQLite, and transitions session to RECORDED.
    """
    initial_answer = session.answers[0] if session.answers else None
    latest_verdict = session.verdicts[-1] if session.verdicts else None

    # Determine outcome & confidence
    if len(session.answers) == 1:
        if latest_verdict and latest_verdict.passed:
            outcome = Outcome.FIRST_TRY_CORRECT
            confidence = initial_answer.self_rating if initial_answer else 4
        else:
            outcome = Outcome.UNRESOLVED
            confidence = min(initial_answer.self_rating if initial_answer else 1, 2)
    else:
        # Follow-up round occurred
        if latest_verdict and latest_verdict.passed:
            outcome = Outcome.RESOLVED_ON_FOLLOW_UP
            confidence = 3  # Matches Beat 6 spec: "Record shows confidence 3 and 'resolved on follow-up'"
        else:
            outcome = Outcome.UNRESOLVED
            confidence = 2

    concept_id = session.question.concept_id if session.question else "recursion_base_case"
    next_review = calculate_next_review(outcome=outcome, confidence=confidence)

    record = ConceptRecord(
        concept_id=concept_id,
        session_id=session.session_id,
        user_id=session.user_id,
        confidence=confidence,
        outcome=outcome,
        attempts_count=len(session.answers),
        next_review_at=next_review,
        notes=f"Completed with {len(session.answers)} attempt(s). Verdict: {'Passed' if latest_verdict and latest_verdict.passed else 'Failed'}",
    )

    session.store.save_concept_record(record)

    session.transition_to(
        State.RECORDED,
        "RECORD_SAVED",
        {
            "record": record.model_dump(),
            "verdict": latest_verdict.model_dump() if latest_verdict else None,
        },
    )
    return record


def step_skip(
    session: FlowSession,
    reason: str = "timeout",
) -> ConceptRecord:
    """
    Executes Skipped step:
    Records timeout or non-response, computes degraded spaced repetition date,
    and transitions session to SKIPPED.
    """
    concept_id = session.question.concept_id if session.question else "recursion_base_case"
    outcome = Outcome.SKIPPED
    confidence = 1
    next_review = calculate_next_review(outcome=outcome, confidence=confidence)

    record = ConceptRecord(
        concept_id=concept_id,
        session_id=session.session_id,
        user_id=session.user_id,
        confidence=confidence,
        outcome=outcome,
        attempts_count=len(session.answers),
        next_review_at=next_review,
        notes=f"Session skipped or timed out: {reason}",
    )

    session.store.save_concept_record(record)

    session.transition_to(
        State.SKIPPED,
        "SESSION_SKIPPED",
        {
            "reason": reason,
            "record": record.model_dump(),
        },
    )
    return record
