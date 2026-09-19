"""
decay.py - Spaced repetition decay scheduling and debug time-travel for MindMesh.

Owns:
- Computing next-review dates based on final confidence and resolution outcome.
- Spaced-repetition scheduling intervals.
- Debug fast-forward mode for demo beats 7 & 8.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from models import ConceptRecord, Outcome


def calculate_next_review(
    outcome: Outcome,
    confidence: int,
    base_time: Optional[datetime] = None,
) -> datetime:
    """
    Computes the spaced repetition review date.
    - first_try_correct with high confidence (4-5) -> 7 days
    - first_try_correct with low/medium confidence (1-3) -> 4 days
    - resolved_on_follow_up -> 2 days (48 hours)
    - unresolved (wrong on follow-up) -> 1 day (24 hours)
    - skipped / timeout -> 12 hours
    """
    now = base_time or datetime.now(timezone.utc)

    if outcome == Outcome.FIRST_TRY_CORRECT:
        days = 7 if confidence >= 4 else 4
        return now + timedelta(days=days)
    elif outcome == Outcome.RESOLVED_ON_FOLLOW_UP:
        return now + timedelta(days=2)
    elif outcome == Outcome.UNRESOLVED:
        return now + timedelta(days=1)
    elif outcome == Outcome.SKIPPED:
        return now + timedelta(hours=12)
    else:
        return now + timedelta(days=1)


def is_due_for_review(
    record: ConceptRecord,
    current_time: Optional[datetime] = None,
) -> bool:
    """Returns True if the concept is due for review based on next_review_at."""
    now = current_time or datetime.now(timezone.utc)
    return now >= record.next_review_at


def fast_forward_record(
    record: ConceptRecord,
    hours: float = 72.0,
) -> ConceptRecord:
    """
    Debug mode time travel:
    Simulates elapsed time by shifting the record's timestamps backwards,
    making the concept immediately due for review for the second encounter demo.
    """
    delta = timedelta(hours=hours)
    updated = record.model_copy()
    updated.created_at = record.created_at - delta
    updated.next_review_at = record.next_review_at - delta
    return updated
