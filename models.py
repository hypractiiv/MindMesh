"""
models.py - Pydantic models and Enums for MindMesh.

Owns: State enum, Answer, Verdict, Question, ConceptRecord, SessionEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import random
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class State(str, Enum):
    PROMPTING = "Prompting"
    ANSWERING = "Answering"
    CHECKING = "Checking"
    WAITING_FOR_FOLLOWUP = "Waiting for follow-up"
    RECORDED = "Recorded"
    SKIPPED = "Skipped"


class Outcome(str, Enum):
    FIRST_TRY_CORRECT = "first_try_correct"
    RESOLVED_ON_FOLLOW_UP = "resolved_on_follow_up"
    UNRESOLVED = "unresolved"
    SKIPPED = "skipped"


class Answer(BaseModel):
    """Represents a student's answer submission."""
    student_answer: str
    self_rating: int = Field(ge=1, le=5, description="Self-assessed confidence rating from 1 to 5")
    attempt_number: int = Field(default=1, ge=1, le=2, description="1 for initial attempt, 2 for follow-up")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Verdict(BaseModel):
    """Evaluator output judging student answer."""
    passed: bool
    objection: Optional[str] = None
    reasoning: Optional[str] = None
    is_mismatch: bool = False


class Question(BaseModel):
    """Concept question specification with dynamic internet retrieval metadata and MCQ options."""
    concept_id: str
    topic_name: Optional[str] = None
    prompt_text: str
    code_context: Optional[str] = None
    options: Optional[Dict[str, str]] = None
    correct_option: Optional[str] = None
    explanation: Optional[str] = None
    follow_up_prompt: Optional[str] = None
    rubric_criteria: Optional[List[str]] = None
    source_url: Optional[str] = None
    quiz_source: Optional[str] = None
    source_provider: Optional[str] = "curated"  # "openai", "gemini", "wikipedia", "offline_fallback", "curated"
    is_fallback: bool = False
    fallback_chain: Optional[List[str]] = None

    def shuffle_options(self, seed: Optional[int] = None) -> Question:
        """
        Returns a new Question with options randomly shuffled among ['A', 'B', 'C', 'D'],
        updating correct_option to match whichever letter the correct text is moved to.
        """
        if not self.options or len(self.options) < 2 or not self.correct_option:
            return self.model_copy()

        rng = random.Random(seed)
        correct_text = self.options.get(self.correct_option)
        keys = ["A", "B", "C", "D"][:len(self.options)]

        values = list(self.options.values())
        rng.shuffle(values)

        new_options = {k: v for k, v in zip(keys, values)}

        # Locate where the correct answer landed
        new_correct_option = self.correct_option
        for k, v in new_options.items():
            if v == correct_text:
                new_correct_option = k
                break

        # Update any explicit "Option X" text in explanation or follow_up_prompt
        new_explanation = self.explanation
        new_follow_up = self.follow_up_prompt
        if self.correct_option and new_correct_option != self.correct_option:
            pat = re.compile(rf"\boption\s+{re.escape(self.correct_option)}\b", re.IGNORECASE)
            rep = f"Option {new_correct_option}"
            if new_explanation:
                new_explanation = pat.sub(rep, new_explanation)
            if new_follow_up:
                new_follow_up = pat.sub(rep, new_follow_up)

        return self.model_copy(update={
            "options": new_options,
            "correct_option": new_correct_option,
            "explanation": new_explanation,
            "follow_up_prompt": new_follow_up,
        })


class User(BaseModel):
    """Registered student account profile."""
    username: str = Field(min_length=3, max_length=30, description="Unique username handle")
    display_name: str = Field(min_length=1, max_length=50, description="Student display name")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConceptRecord(BaseModel):
    """Persistent summary record for a completed concept encounter."""
    concept_id: str
    session_id: str
    user_id: str = Field(default="default_student", description="Associated student account ID")
    confidence: int = Field(ge=1, le=5)
    outcome: Outcome
    attempts_count: int = Field(ge=1, le=2)
    next_review_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class SessionEvent(BaseModel):
    """Append-only audit trail event stored in SQLite."""
    id: Optional[int] = None
    session_id: str
    user_id: str = Field(default="default_student", description="Associated student account ID")
    step: int
    state: State
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
