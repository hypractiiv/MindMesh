from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from steps import (
    Answer,
    ConceptRecord,
    Verdict,
    answer_capture,
    evaluate,
    follow_up,
    record_concept,
    should_ask_follow_up,
)
from store import Store


PROMPTING = "Prompting"
ANSWERING = "Answering"
CHECKING = "Checking"
WAITING_FOLLOW_UP = "Waiting for follow-up"
RECORDED = "Recorded"
SKIPPED = "Skipped"


@dataclass
class TransitionResult:
    session_id: str
    state: str
    message: str


class ReviewFlow:
    def __init__(self, store: Store, today: date | None = None) -> None:
        self.store = store
        self.today = today or date.today()

    def start(self, *, concept: str, question: str) -> TransitionResult:
        session_id = str(uuid4())
        self.store.create_session(
            session_id=session_id,
            concept=concept,
            question=question,
            state=ANSWERING,
            attempt=0,
        )
        return TransitionResult(session_id=session_id, state=ANSWERING, message=question)

    def submit_answer(self, *, session_id: str, text: str, self_rating: int | None) -> TransitionResult:
        session = self._must_get_session(session_id)
        if session.state not in (ANSWERING, WAITING_FOLLOW_UP):
            raise ValueError(f"Cannot submit answer while session is in '{session.state}'")

        attempt = session.attempt + 1
        answer = answer_capture(concept=session.concept, text=text, self_rating=self_rating, attempt=attempt)
        self.store.append_record(session_id=session_id, concept=session.concept, kind="answer", payload=answer.model_dump())

        self.store.update_session(session_id, state=CHECKING, attempt=attempt)
        verdict = evaluate(answer)
        self.store.append_record(session_id=session_id, concept=session.concept, kind="verdict", payload=verdict.model_dump())

        if verdict.passed:
            concept_record = self._persist_record(session_id=session_id, concept=session.concept)
            self.store.update_session(session_id, state=RECORDED)
            return TransitionResult(
                session_id=session_id,
                state=RECORDED,
                message=(
                    f"Recorded confidence={concept_record.confidence}, next_review={concept_record.next_review.isoformat()}"
                ),
            )

        if attempt == 1 and should_ask_follow_up(answer, verdict):
            question = follow_up(objection=verdict.objection or "")
            self.store.append_record(session_id=session_id, concept=session.concept, kind="question", payload=question.model_dump())
            self.store.update_session(session_id, state=WAITING_FOLLOW_UP)
            return TransitionResult(session_id=session_id, state=WAITING_FOLLOW_UP, message=question.text)

        if attempt >= 2:
            return self._skip(session_id=session_id, reason="follow-up failed")

        return self._skip(session_id=session_id, reason="initial answer incorrect")

    def resume(self, *, session_id: str) -> TransitionResult:
        session = self._must_get_session(session_id)
        if session.state in (ANSWERING, WAITING_FOLLOW_UP):
            return TransitionResult(session_id=session_id, state=session.state, message=session.question)
        if session.state in (RECORDED, SKIPPED):
            return TransitionResult(session_id=session_id, state=session.state, message="Session already finished")
        raise ValueError(f"Unsupported state: {session.state}")

    def timeout(self, *, session_id: str) -> TransitionResult:
        session = self._must_get_session(session_id)
        if session.state not in (ANSWERING, WAITING_FOLLOW_UP):
            return TransitionResult(session_id=session_id, state=session.state, message="No timeout action needed")
        return self._skip(session_id=session_id, reason="timeout")

    def _skip(self, *, session_id: str, reason: str) -> TransitionResult:
        session = self._must_get_session(session_id)
        answers = [Answer(**row) for row in self.store.get_records(session_id=session_id, kind="answer")]
        verdicts = [Verdict(**row) for row in self.store.get_records(session_id=session_id, kind="verdict")]
        concept_record = record_concept(
            concept=session.concept,
            answers=answers,
            verdicts=verdicts,
            reviewed_on=self.today,
            skipped=True,
        )
        payload = concept_record.model_dump()
        payload["last_reviewed"] = concept_record.last_reviewed.isoformat()
        payload["next_review"] = concept_record.next_review.isoformat()
        payload["status"] = SKIPPED
        payload["reason"] = reason
        self.store.append_record(session_id=session_id, concept=session.concept, kind="record", payload=payload)
        self.store.update_session(session_id, state=SKIPPED)
        return TransitionResult(session_id=session_id, state=SKIPPED, message="Session skipped")

    def _persist_record(self, *, session_id: str, concept: str) -> ConceptRecord:
        answers = [Answer(**row) for row in self.store.get_records(session_id=session_id, kind="answer")]
        verdicts = [Verdict(**row) for row in self.store.get_records(session_id=session_id, kind="verdict")]
        concept_record = record_concept(
            concept=concept,
            answers=answers,
            verdicts=verdicts,
            reviewed_on=self.today,
        )
        payload = concept_record.model_dump()
        payload["last_reviewed"] = concept_record.last_reviewed.isoformat()
        payload["next_review"] = concept_record.next_review.isoformat()
        payload["status"] = RECORDED
        self.store.append_record(session_id=session_id, concept=concept, kind="record", payload=payload)
        return concept_record

    def _must_get_session(self, session_id: str):
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(f"Unknown session_id: {session_id}")
        return session
