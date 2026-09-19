# MindMesh System Specification

## 1. System Overview
**MindMesh** is a persistent, single-concept learning-confidence tracker designed for the Agentathon 2026.
It evaluates a student's answer to a recursive list summation problem, compares demonstrated correctness against self-reported confidence (1–5 scale), and triggers an adaptive backward state transition when disagreement is detected.

The system is deliberately scoped:
- Tracks a single concept (`recursion_base_case`) to prove the stateful loop.
- Does **not** teach the concept or provide answers.
- Centralizes all model calls through a single bounded boundary.
- Enforces strict spend caps (max 4 calls/session) and revision caps (max 1 follow-up round).
- Persists all events and encounter records in SQLite.

---

## 2. The Six-State Machine Flow

| State | What Happens | Exit Condition |
| :--- | :--- | :--- |
| **Prompting** | System selects the concept due for review and shows the question. | Question is shown (`QUESTION_LOADED`) |
| **Answering** | Student submits answer and self-rating (1–5). | Answer submitted or timeout/skip |
| **Checking** | Evaluator assesses answer and, on attempt 1, checks for confidence mismatch. | Verdict exists |
| **Waiting for follow-up** | System asks one targeted follow-up question and waits for human input. | Follow-up answer or timeout |
| **Recorded** | Confidence, outcome, and next-review date are persisted to SQLite. | Finished |
| **Skipped** | Timeout/non-response is recorded and decay is accelerated. | Finished |

### Critical Transitions
- `Checking` $\to$ `Recorded`: If the student's answer passes.
- `Checking` $\to$ `Waiting for follow-up`: If answer fails AND student self-rating $\ge 4$ on Attempt 1.
- `Waiting for follow-up` $\to$ `Checking`: Student provides a follow-up answer (Attempt 2).
- `Checking` $\to$ `Recorded`: If Attempt 2 is evaluated (revision limit exhausted).
- `Answering` / `Waiting for follow-up` $\to$ `Skipped`: On timeout or explicit skip.

---

## 3. Data Model

### `State` (Enum)
`Prompting`, `Answering`, `Checking`, `Waiting for follow-up`, `Recorded`, `Skipped`.

### `Outcome` (Enum)
`first_try_correct`, `resolved_on_follow_up`, `unresolved`, `skipped`.

### `Answer` (Pydantic)
- `student_answer`: `str`
- `self_rating`: `int` (1..5)
- `attempt_number`: `int` (1..2)
- `timestamp`: `datetime`

### `Verdict` (Pydantic)
- `passed`: `bool`
- `objection`: `Optional[str]`
- `reasoning`: `Optional[str]`
- `is_mismatch`: `bool`

### `ConceptRecord` (Pydantic & SQLite Table)
- `concept_id`: `str`
- `session_id`: `str` (unique per session)
- `confidence`: `int` (1..5)
- `outcome`: `Outcome`
- `attempts_count`: `int` (1..2)
- `next_review_at`: `datetime`
- `created_at`: `datetime`

### `SessionEvent` (Pydantic & SQLite Table)
- `id`: `Optional[int]`
- `session_id`: `str`
- `step`: `int`
- `state`: `State`
- `event_type`: `str`
- `payload`: `Dict[str, Any]`
- `timestamp`: `datetime`

---

## 4. Spaced Repetition Intervals (`decay.py`)
- `first_try_correct` ($\text{confidence} \ge 4$): $+7$ days
- `first_try_correct` ($\text{confidence} < 4$): $+4$ days
- `resolved_on_follow_up`: $+2$ days ($+48$ hours)
- `unresolved`: $+1$ day ($+24$ hours)
- `skipped`: $+12$ hours
- Debug Mode: `fast_forward_record(hours=72)` simulates elapsed time to make the concept due immediately.

---

## 5. Security & Prompt Defense
- Centralized boundary in `llm.py`.
- Student inputs are encapsulated within `<STUDENT_ANSWER>` delimiters.
- Evaluator system prompt directs the LLM to treat content strictly as untrusted evaluation data.
- Hard spend cap: Maximum 4 calls per session. Attempting a 5th call raises `SpendLimitExceededError`.
