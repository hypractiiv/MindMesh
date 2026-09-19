"""
store.py - Append-only SQLite persistence layer for MindMesh.

Owns: SQLite schema, event append/read, concept records, session resumption.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from models import ConceptRecord, Outcome, SessionEvent, State


DEFAULT_DB_PATH = Path(__file__).parent / "mindmesh.db"


class MindMeshStore:
    """Manages persistent SQLite storage with append-only event logging and recovery."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.init_db()

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database schema with tables and indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_events_session_id 
                ON session_events(session_id);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS concept_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id TEXT NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    confidence INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    attempts_count INTEGER NOT NULL,
                    next_review_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    notes TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_concept_records_concept_id 
                ON concept_records(concept_id);
            """)
            conn.commit()

    def append_event(
        self,
        session_id: str,
        step: int,
        state: State,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> SessionEvent:
        """Appends an immutable event to the session event audit log."""
        ts = timestamp or datetime.now(timezone.utc)
        payload_data = payload or {}
        payload_json = json.dumps(payload_data, default=str)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO session_events (session_id, step, state, event_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, step, state.value, event_type, payload_json, ts.isoformat()),
            )
            event_id = cursor.lastrowid
            conn.commit()

        return SessionEvent(
            id=event_id,
            session_id=session_id,
            step=step,
            state=state,
            event_type=event_type,
            payload=payload_data,
            timestamp=ts,
        )

    def get_session_events(self, session_id: str) -> List[SessionEvent]:
        """Reads all events for a given session in chronological order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, step, state, event_type, payload_json, timestamp
                FROM session_events
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = cursor.fetchall()

        events = []
        for r in rows:
            events.append(
                SessionEvent(
                    id=r["id"],
                    session_id=r["session_id"],
                    step=r["step"],
                    state=State(r["state"]),
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"]),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                )
            )
        return events

    def get_all_session_events(self) -> List[SessionEvent]:
        """Reads all events across all sessions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, step, state, event_type, payload_json, timestamp
                FROM session_events
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()

        return [
            SessionEvent(
                id=r["id"],
                session_id=r["session_id"],
                step=r["step"],
                state=State(r["state"]),
                event_type=r["event_type"],
                payload=json.loads(r["payload_json"]),
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    def save_concept_record(self, record: ConceptRecord) -> None:
        """Saves or updates a persistent concept review record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO concept_records 
                (concept_id, session_id, confidence, outcome, attempts_count, next_review_at, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.concept_id,
                    record.session_id,
                    record.confidence,
                    record.outcome.value,
                    record.attempts_count,
                    record.next_review_at.isoformat(),
                    record.created_at.isoformat(),
                    record.notes,
                ),
            )
            conn.commit()

    def get_concept_records(self, concept_id: str) -> List[ConceptRecord]:
        """Returns full historical encounter records for a concept (never only the latest)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT concept_id, session_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                FROM concept_records
                WHERE concept_id = ?
                ORDER BY created_at ASC
                """,
                (concept_id,),
            )
            rows = cursor.fetchall()

        records = []
        for r in rows:
            records.append(
                ConceptRecord(
                    concept_id=r["concept_id"],
                    session_id=r["session_id"],
                    confidence=r["confidence"],
                    outcome=Outcome(r["outcome"]),
                    attempts_count=r["attempts_count"],
                    next_review_at=datetime.fromisoformat(r["next_review_at"]),
                    created_at=datetime.fromisoformat(r["created_at"]),
                    notes=r["notes"],
                )
            )
        return records

    def get_latest_concept_record(self, concept_id: str) -> Optional[ConceptRecord]:
        """Returns the most recent encounter record for a concept, if any exists."""
        records = self.get_concept_records(concept_id)
        return records[-1] if records else None

    def resume_session(self, session_id: str) -> Dict[str, Any]:
        """
        Reconstructs the full session state machine context from SQLite events.
        Enables process crash recovery without losing historical inputs or state.
        """
        events = self.get_session_events(session_id)
        if not events:
            return {
                "session_id": session_id,
                "exists": False,
                "current_state": None,
                "current_step": 0,
                "answers": [],
                "verdicts": [],
                "question": None,
                "is_terminated": False,
            }

        current_state = events[-1].state
        current_step = events[-1].step
        answers: List[Dict[str, Any]] = []
        verdicts: List[Dict[str, Any]] = []
        question: Optional[Dict[str, Any]] = None

        for ev in events:
            if "question" in ev.payload and ev.payload["question"]:
                question = ev.payload.get("question")
            if "answer" in ev.payload and ev.payload["answer"]:
                answers.append(ev.payload.get("answer"))
            if "verdict" in ev.payload and ev.payload["verdict"]:
                verdicts.append(ev.payload.get("verdict"))

        is_terminated = current_state in (State.RECORDED, State.SKIPPED)

        return {
            "session_id": session_id,
            "exists": True,
            "current_state": current_state,
            "current_step": current_step,
            "answers": [a for a in answers if a is not None],
            "verdicts": [v for v in verdicts if v is not None],
            "question": question,
            "is_terminated": is_terminated,
            "events_count": len(events),
        }
