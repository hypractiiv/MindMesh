"""
flow.py - State machine runner and transition rules for MindMesh.

Owns: 6 states and transitions, mismatch and timeout edges, single follow-up limit.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from models import Answer, Question, State, Verdict
from store import MindMeshStore


VALID_TRANSITIONS: Dict[State, List[State]] = {
    State.PROMPTING: [State.ANSWERING],
    State.ANSWERING: [State.CHECKING, State.SKIPPED],
    State.CHECKING: [State.WAITING_FOR_FOLLOWUP, State.RECORDED],
    State.WAITING_FOR_FOLLOWUP: [State.CHECKING, State.SKIPPED],
    State.RECORDED: [],  # Terminal
    State.SKIPPED: [],   # Terminal
}


class InvalidStateTransition(Exception):
    """Raised when an illegal transition is attempted in the state machine."""
    pass


class FlowSession:
    """State machine session tracking active state, student identity, history, and transitions."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        store: Optional[MindMeshStore] = None,
        initial_state: State = State.PROMPTING,
        user_id: str = "default_student",
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.store = store or MindMeshStore()
        self.state: State = initial_state
        self.user_id: str = user_id
        self.step_count: int = 0
        self.question: Optional[Question] = None
        self.answers: List[Answer] = []
        self.verdicts: List[Verdict] = []

    @classmethod
    def resume(cls, session_id: str, store: Optional[MindMeshStore] = None) -> FlowSession:
        """Resumes an existing session from persistent SQLite events with student identity intact."""
        active_store = store or MindMeshStore()
        snapshot = active_store.resume_session(session_id)
        if not snapshot["exists"]:
            raise ValueError(f"Session {session_id} not found in database.")

        instance = cls(
            session_id=session_id,
            store=active_store,
            initial_state=snapshot["current_state"],
            user_id=snapshot.get("user_id", "default_student"),
        )
        instance.step_count = snapshot["current_step"]

        if snapshot["question"]:
            instance.question = Question(**snapshot["question"])

        instance.answers = [Answer(**a) for a in snapshot["answers"]]
        instance.verdicts = [Verdict(**v) for v in snapshot["verdicts"]]
        return instance

    @property
    def is_terminated(self) -> bool:
        return self.state in (State.RECORDED, State.SKIPPED)

    @property
    def attempt_count(self) -> int:
        """Revision limit is strictly based on stored answer records, not volatile memory."""
        return len(self.answers)

    def can_transition(self, to_state: State) -> bool:
        return to_state in VALID_TRANSITIONS.get(self.state, [])

    def transition_to(
        self,
        to_state: State,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Executes and persists a state machine transition."""
        if not self.can_transition(to_state):
            raise InvalidStateTransition(
                f"Cannot transition from {self.state.value} to {to_state.value}. "
                f"Allowed transitions: {[s.value for s in VALID_TRANSITIONS.get(self.state, [])]}"
            )

        self.step_count += 1
        self.state = to_state
        self.store.append_event(
            session_id=self.session_id,
            user_id=self.user_id,
            step=self.step_count,
            state=self.state,
            event_type=event_type,
            payload=payload or {},
        )

    def determine_checking_exit(self, verdict: Verdict) -> State:
        """
        Determines the next state from CHECKING.
        Rule:
        - If answer passed -> RECORDED
        - If answer failed and mismatch detected on attempt 1 (student self_rating >= 4)
          AND revision limit (1 follow-up round) not exceeded -> WAITING_FOR_FOLLOWUP
        - Otherwise (answer failed without mismatch, or attempt 2 follow-up exhausted) -> RECORDED
        """
        if verdict.passed:
            return State.RECORDED

        # Enforce max 1 follow-up round: attempt_count == 1 allows follow-up if mismatch
        if self.attempt_count <= 1 and verdict.is_mismatch:
            return State.WAITING_FOR_FOLLOWUP

        return State.RECORDED
