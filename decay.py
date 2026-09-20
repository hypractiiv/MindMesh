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


def get_review_interval_hours(outcome: Outcome, confidence: int) -> float:
    """
    Calculates review interval in hours based on confidence levels (1-5) and outcome:
    - First-try correct:
        * Confidence 5 (Mastery): 7 days (168h)
        * Confidence 4 (Strong): 5 days (120h)
        * Confidence 3 (Moderate): 3 days (72h)
        * Confidence 2 (Low/Hesitant): 2 days (48h)
        * Confidence 1 (Lucky Guess): 1 day (24h)
    - Resolved on follow-up:
        * Confidence 4-5: 3 days (72h)
        * Confidence 3: 2 days (48h)
        * Confidence 1-2: 1 day (24h)
    - Unresolved (Failed follow-up):
        * Confidence 4-5 (Blind spot! Overconfident): 18 hours (urgent reinforcement)
        * Confidence 1-3 (Needs study): 24 hours (1 day)
    - Skipped / Abandoned:
        * 12 hours
    """
    clamped_conf = max(1, min(5, confidence))

    if outcome == Outcome.FIRST_TRY_CORRECT:
        if clamped_conf >= 5:
            return 168.0  # 7 days
        elif clamped_conf == 4:
            return 120.0  # 5 days
        elif clamped_conf == 3:
            return 72.0   # 3 days
        elif clamped_conf == 2:
            return 48.0   # 2 days
        else:
            return 24.0   # 1 day

    elif outcome == Outcome.RESOLVED_ON_FOLLOW_UP:
        if clamped_conf >= 4:
            return 72.0   # 3 days
        elif clamped_conf == 3:
            return 48.0   # 2 days
        else:
            return 24.0   # 1 day

    elif outcome == Outcome.UNRESOLVED:
        if clamped_conf >= 4:
            return 18.0   # 18 hours (blind spot priority)
        else:
            return 24.0   # 24 hours

    elif outcome == Outcome.SKIPPED:
        return 12.0

    return 24.0


def calculate_next_review(
    outcome: Outcome,
    confidence: int,
    base_time: Optional[datetime] = None,
) -> datetime:
    """
    Computes the spaced repetition review date calculated directly from confidence levels and outcomes.
    """
    now = base_time or datetime.now(timezone.utc)
    hours = get_review_interval_hours(outcome=outcome, confidence=confidence)
    return now + timedelta(hours=hours)


def get_review_interval_description(outcome: Outcome, confidence: int) -> str:
    """Returns human-readable explanation of why this review date was chosen based on confidence."""
    hours = get_review_interval_hours(outcome, confidence)
    days = hours / 24.0
    if days >= 1.0 and hours % 24 == 0:
        time_str = f"{int(days)} day{'s' if days > 1 else ''}"
    else:
        time_str = f"{int(hours)} hours"

    if outcome == Outcome.FIRST_TRY_CORRECT:
        return f"{time_str} (First-try correct with confidence {confidence}/5)"
    elif outcome == Outcome.RESOLVED_ON_FOLLOW_UP:
        return f"{time_str} (Corrected on follow-up with confidence {confidence}/5)"
    elif outcome == Outcome.UNRESOLVED:
        return f"{time_str} (Needs reinforcement after incorrect attempt)"
    elif outcome == Outcome.SKIPPED:
        return f"{time_str} (Skipped session)"
    return f"{time_str} (Review scheduled)"


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
