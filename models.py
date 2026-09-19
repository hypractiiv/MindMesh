"""
models.py - Pydantic models and Enums for MindMesh.

Owns: State enum, Answer, Verdict, Question, ConceptRecord, SessionEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
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
    """Concept question specification with dynamic internet retrieval metadata."""
    concept_id: str
    topic_name: Optional[str] = None
    prompt_text: str
    code_context: Optional[str] = None
    follow_up_prompt: Optional[str] = None
    rubric_criteria: Optional[List[str]] = None
    source_url: Optional[str] = None


class ConceptRecord(BaseModel):
    """Persistent summary record for a completed concept encounter."""
    concept_id: str
    session_id: str
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
    step: int
    state: State
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
