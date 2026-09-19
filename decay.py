from __future__ import annotations

from datetime import date, timedelta

_BASE_INTERVALS = {
    1: 1,
    2: 2,
    3: 4,
    4: 7,
    5: 10,
}


def calculate_next_review(
    confidence: int,
    *,
    last_reviewed: date,
    unresolved: bool = False,
) -> date:
    """Return a deterministic next-review date from confidence and outcome."""
    bounded_confidence = max(1, min(5, confidence))
    interval_days = _BASE_INTERVALS[bounded_confidence]
    if unresolved:
        interval_days = max(1, interval_days // 2)
    return last_reviewed + timedelta(days=interval_days)
