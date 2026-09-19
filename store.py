"""
store.py - Append-only SQLite persistence layer for MindMesh.

Owns: SQLite schema, event append/read, concept records, session resumption.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from models import ConceptRecord, Outcome, SessionEvent, State, User


DEFAULT_DB_PATH = Path(__file__).parent / "mindmesh.db"
PASSWORD_HASH_ITERATIONS = 200_000


def _salt_to_bytes(salt: str) -> bytes:
    try:
        return bytes.fromhex(salt)
    except ValueError:
        return salt.encode("utf-8")


class MindMeshStore:
    """Manages persistent SQLite storage with append-only event logging, recovery, and user accounts."""

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
        """Initialize database schema with tables, indexes, and user accounts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # 2. Session events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default_student',
                    step INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
            """)

            # 3. Concept records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS concept_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id TEXT NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL DEFAULT 'default_student',
                    confidence INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    attempts_count INTEGER NOT NULL,
                    next_review_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    notes TEXT
                );
            """)

            # Perform column migrations on existing tables BEFORE creating indexes on them
            cursor.execute("PRAGMA table_info(session_events);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE session_events ADD COLUMN user_id TEXT DEFAULT 'default_student';")

            cursor.execute("PRAGMA table_info(concept_records);")
            rec_columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in rec_columns:
                cursor.execute("ALTER TABLE concept_records ADD COLUMN user_id TEXT DEFAULT 'default_student';")

            # Indexes (now guaranteed to have all referenced columns present)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_events_session_id 
                ON session_events(session_id);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_concept_records_concept_user 
                ON concept_records(concept_id, user_id);
            """)

            conn.commit()

    # --- User Account Management ---

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        salt_bytes = _salt_to_bytes(salt)
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            PASSWORD_HASH_ITERATIONS,
        ).hex()

    def create_user(self, username: str, display_name: str, password: str) -> Optional[User]:
        """Creates a new student account with salted password hashing."""
        clean_user = username.strip().lower()
        if not clean_user or len(clean_user) < 3 or len(password) < 3:
            return None

        salt = secrets.token_hex(16)
        pwd_hash = self._hash_password(password, salt)
        now = datetime.now(timezone.utc)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (username, display_name, password_hash, salt, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean_user, display_name.strip(), pwd_hash, salt, now.isoformat()),
                )
                conn.commit()
            return User(username=clean_user, display_name=display_name.strip(), created_at=now)
        except sqlite3.IntegrityError:
            # Username already taken
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticates credentials against stored salted hash."""
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, display_name, password_hash, salt, created_at FROM users WHERE username = ?",
                (clean_user,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        expected_hash = self._hash_password(password, row["salt"])
        if hmac.compare_digest(expected_hash, row["password_hash"]):
            return User(
                username=row["username"],
                display_name=row["display_name"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        return None

    def get_user(self, username: str) -> Optional[User]:
        """Fetches a user profile by username."""
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, display_name, created_at FROM users WHERE username = ?", (clean_user,))
            row = cursor.fetchone()

        if row:
            return User(
                username=row["username"],
                display_name=row["display_name"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        return None

    def list_users(self) -> List[User]:
        """Lists all registered student profiles."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, display_name, created_at FROM users ORDER BY created_at ASC")
            rows = cursor.fetchall()

        return [
            User(
                username=r["username"],
                display_name=r["display_name"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def append_event(
        self,
        session_id: str,
        step: int,
        state: State,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        user_id: str = "default_student",
    ) -> SessionEvent:
        """Appends an immutable event to the session event audit log."""
        ts = timestamp or datetime.now(timezone.utc)
        payload_data = payload or {}
        payload_json = json.dumps(payload_data, default=str)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO session_events (session_id, user_id, step, state, event_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, step, state.value, event_type, payload_json, ts.isoformat()),
            )
            event_id = cursor.lastrowid
            conn.commit()

        return SessionEvent(
            id=event_id,
            session_id=session_id,
            user_id=user_id,
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
                SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
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
                    user_id=r["user_id"] if "user_id" in r.keys() else "default_student",
                    step=r["step"],
                    state=State(r["state"]),
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"]),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                )
            )
        return events

    def get_all_session_events(self, user_id: Optional[str] = None) -> List[SessionEvent]:
        """Reads all events across all sessions, optionally filtered by student."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    """
                    SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
                    FROM session_events
                    WHERE user_id = ?
                    ORDER BY id ASC
                    """,
                    (user_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
                    FROM session_events
                    ORDER BY id ASC
                    """
                )
            rows = cursor.fetchall()

        return [
            SessionEvent(
                id=r["id"],
                session_id=r["session_id"],
                user_id=r["user_id"] if "user_id" in r.keys() else "default_student",
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
                (concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.concept_id,
                    record.session_id,
                    record.user_id,
                    record.confidence,
                    record.outcome.value,
                    record.attempts_count,
                    record.next_review_at.isoformat(),
                    record.created_at.isoformat(),
                    record.notes,
                ),
            )
            conn.commit()

    def get_concept_records(self, concept_id: str, user_id: Optional[str] = None) -> List[ConceptRecord]:
        """Returns full historical encounter records for a concept, optionally isolated per student."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    """
                    SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                    FROM concept_records
                    WHERE concept_id = ? AND user_id = ?
                    ORDER BY created_at ASC
                    """,
                    (concept_id, user_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
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
                    user_id=r["user_id"] if "user_id" in r.keys() else "default_student",
                    confidence=r["confidence"],
                    outcome=Outcome(r["outcome"]),
                    attempts_count=r["attempts_count"],
                    next_review_at=datetime.fromisoformat(r["next_review_at"]),
                    created_at=datetime.fromisoformat(r["created_at"]),
                    notes=r["notes"],
                )
            )
        return records

    def get_latest_concept_record(self, concept_id: str, user_id: Optional[str] = None) -> Optional[ConceptRecord]:
        """Returns the most recent encounter record for a concept and student, if any exists."""
        records = self.get_concept_records(concept_id, user_id=user_id)
        return records[-1] if records else None

    def get_user_records(self, user_id: str) -> List[ConceptRecord]:
        """Returns all completed concept review records for a given student."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                FROM concept_records
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        return [
            ConceptRecord(
                concept_id=r["concept_id"],
                session_id=r["session_id"],
                user_id=r["user_id"],
                confidence=r["confidence"],
                outcome=Outcome(r["outcome"]),
                attempts_count=r["attempts_count"],
                next_review_at=datetime.fromisoformat(r["next_review_at"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                notes=r["notes"],
            )
            for r in rows
        ]

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
        user_id = events[-1].user_id
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
            "user_id": user_id,
            "exists": True,
            "current_state": current_state,
            "current_step": current_step,
            "answers": [a for a in answers if a is not None],
            "verdicts": [v for v in verdicts if v is not None],
            "question": question,
            "is_terminated": is_terminated,
            "events_count": len(events),
        }

    @property
    def engine_name(self) -> str:
        return "SQLite"


class PostgresStore:
    """PostgreSQL storage engine with connection pooling, native JSONB, and upsert handling."""

    def __init__(self, db_url: Optional[str] = None):
        import os
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL must be provided for PostgresStore.")
        self.init_db()

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[Any, None, None]:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize PostgreSQL schema and tables."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(50) PRIMARY KEY,
                        display_name VARCHAR(100) NOT NULL,
                        password_hash VARCHAR(64) NOT NULL,
                        salt VARCHAR(32) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    );
                """)

                # 2. Session events table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS session_events (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(100) NOT NULL,
                        user_id VARCHAR(50) NOT NULL DEFAULT 'default_student',
                        step INT NOT NULL,
                        state VARCHAR(50) NOT NULL,
                        event_type VARCHAR(100) NOT NULL,
                        payload_json JSONB NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL
                    );
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_session_events_session_id 
                    ON session_events(session_id);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_session_events_user_id 
                    ON session_events(user_id);
                """)

                # 3. Concept records table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS concept_records (
                        id SERIAL PRIMARY KEY,
                        concept_id VARCHAR(100) NOT NULL,
                        session_id VARCHAR(100) NOT NULL UNIQUE,
                        user_id VARCHAR(50) NOT NULL DEFAULT 'default_student',
                        confidence INT NOT NULL,
                        outcome VARCHAR(50) NOT NULL,
                        attempts_count INT NOT NULL,
                        next_review_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        notes TEXT
                    );
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_concept_records_concept_user 
                    ON concept_records(concept_id, user_id);
                """)
                conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        salt_bytes = _salt_to_bytes(salt)
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            PASSWORD_HASH_ITERATIONS,
        ).hex()

    def create_user(self, username: str, display_name: str, password: str) -> Optional[User]:
        clean_user = username.strip().lower()
        if not clean_user or len(clean_user) < 3 or len(password) < 3:
            return None

        salt = secrets.token_hex(16)
        pwd_hash = self._hash_password(password, salt)
        now = datetime.now(timezone.utc)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (username, display_name, password_hash, salt, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (clean_user, display_name.strip(), pwd_hash, salt, now),
                    )
                    conn.commit()
            return User(username=clean_user, display_name=display_name.strip(), created_at=now)
        except Exception:
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT username, display_name, password_hash, salt, created_at FROM users WHERE username = %s",
                    (clean_user,),
                )
                row = cursor.fetchone()

        if not row:
            return None

        expected_hash = self._hash_password(password, row["salt"])
        if hmac.compare_digest(expected_hash, row["password_hash"]):
            ts = row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"]))
            return User(username=row["username"], display_name=row["display_name"], created_at=ts)
        return None

    def get_user(self, username: str) -> Optional[User]:
        clean_user = username.strip().lower()
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT username, display_name, created_at FROM users WHERE username = %s", (clean_user,))
                row = cursor.fetchone()

        if row:
            ts = row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"]))
            return User(username=row["username"], display_name=row["display_name"], created_at=ts)
        return None

    def list_users(self) -> List[User]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT username, display_name, created_at FROM users ORDER BY created_at ASC")
                rows = cursor.fetchall()

        return [
            User(
                username=r["username"],
                display_name=r["display_name"],
                created_at=r["created_at"] if isinstance(r["created_at"], datetime) else datetime.fromisoformat(str(r["created_at"])),
            )
            for r in rows
        ]

    def append_event(
        self,
        session_id: str,
        step: int,
        state: State,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        user_id: str = "default_student",
    ) -> SessionEvent:
        ts = timestamp or datetime.now(timezone.utc)
        payload_data = payload or {}
        payload_json = json.dumps(payload_data, default=str)

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO session_events (session_id, user_id, step, state, event_type, payload_json, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (session_id, user_id, step, state.value, event_type, payload_json, ts),
                )
                event_id = cursor.fetchone()["id"]
                conn.commit()

        return SessionEvent(
            id=event_id,
            session_id=session_id,
            user_id=user_id,
            step=step,
            state=state,
            event_type=event_type,
            payload=payload_data,
            timestamp=ts,
        )

    def get_session_events(self, session_id: str) -> List[SessionEvent]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
                    FROM session_events
                    WHERE session_id = %s
                    ORDER BY id ASC
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall()

        events = []
        for r in rows:
            p = r["payload_json"]
            payload_dict = p if isinstance(p, dict) else json.loads(p)
            ts = r["timestamp"] if isinstance(r["timestamp"], datetime) else datetime.fromisoformat(str(r["timestamp"]))
            events.append(
                SessionEvent(
                    id=r["id"],
                    session_id=r["session_id"],
                    user_id=r.get("user_id", "default_student"),
                    step=r["step"],
                    state=State(r["state"]),
                    event_type=r["event_type"],
                    payload=payload_dict,
                    timestamp=ts,
                )
            )
        return events

    def get_all_session_events(self, user_id: Optional[str] = None) -> List[SessionEvent]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                if user_id:
                    cursor.execute(
                        """
                        SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
                        FROM session_events
                        WHERE user_id = %s
                        ORDER BY id ASC
                        """,
                        (user_id,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, session_id, user_id, step, state, event_type, payload_json, timestamp
                        FROM session_events
                        ORDER BY id ASC
                        """
                    )
                rows = cursor.fetchall()

        events = []
        for r in rows:
            p = r["payload_json"]
            payload_dict = p if isinstance(p, dict) else json.loads(p)
            ts = r["timestamp"] if isinstance(r["timestamp"], datetime) else datetime.fromisoformat(str(r["timestamp"]))
            events.append(
                SessionEvent(
                    id=r["id"],
                    session_id=r["session_id"],
                    user_id=r.get("user_id", "default_student"),
                    step=r["step"],
                    state=State(r["state"]),
                    event_type=r["event_type"],
                    payload=payload_dict,
                    timestamp=ts,
                )
            )
        return events

    def save_concept_record(self, record: ConceptRecord) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO concept_records 
                    (concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        outcome = EXCLUDED.outcome,
                        attempts_count = EXCLUDED.attempts_count,
                        next_review_at = EXCLUDED.next_review_at,
                        created_at = EXCLUDED.created_at,
                        notes = EXCLUDED.notes
                    """,
                    (
                        record.concept_id,
                        record.session_id,
                        record.user_id,
                        record.confidence,
                        record.outcome.value,
                        record.attempts_count,
                        record.next_review_at,
                        record.created_at,
                        record.notes,
                    ),
                )
                conn.commit()

    def get_concept_records(self, concept_id: str, user_id: Optional[str] = None) -> List[ConceptRecord]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                if user_id:
                    cursor.execute(
                        """
                        SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                        FROM concept_records
                        WHERE concept_id = %s AND user_id = %s
                        ORDER BY created_at ASC
                        """,
                        (concept_id, user_id),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                        FROM concept_records
                        WHERE concept_id = %s
                        ORDER BY created_at ASC
                        """,
                        (concept_id,),
                    )
                rows = cursor.fetchall()

        records = []
        for r in rows:
            next_ts = r["next_review_at"] if isinstance(r["next_review_at"], datetime) else datetime.fromisoformat(str(r["next_review_at"]))
            created_ts = r["created_at"] if isinstance(r["created_at"], datetime) else datetime.fromisoformat(str(r["created_at"]))
            records.append(
                ConceptRecord(
                    concept_id=r["concept_id"],
                    session_id=r["session_id"],
                    user_id=r.get("user_id", "default_student"),
                    confidence=r["confidence"],
                    outcome=Outcome(r["outcome"]),
                    attempts_count=r["attempts_count"],
                    next_review_at=next_ts,
                    created_at=created_ts,
                    notes=r.get("notes"),
                )
            )
        return records

    def get_latest_concept_record(self, concept_id: str, user_id: Optional[str] = None) -> Optional[ConceptRecord]:
        records = self.get_concept_records(concept_id, user_id=user_id)
        return records[-1] if records else None

    def get_user_records(self, user_id: str) -> List[ConceptRecord]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT concept_id, session_id, user_id, confidence, outcome, attempts_count, next_review_at, created_at, notes
                    FROM concept_records
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                rows = cursor.fetchall()

        records = []
        for r in rows:
            next_ts = r["next_review_at"] if isinstance(r["next_review_at"], datetime) else datetime.fromisoformat(str(r["next_review_at"]))
            created_ts = r["created_at"] if isinstance(r["created_at"], datetime) else datetime.fromisoformat(str(r["created_at"]))
            records.append(
                ConceptRecord(
                    concept_id=r["concept_id"],
                    session_id=r["session_id"],
                    user_id=r.get("user_id", "default_student"),
                    confidence=r["confidence"],
                    outcome=Outcome(r["outcome"]),
                    attempts_count=r["attempts_count"],
                    next_review_at=next_ts,
                    created_at=created_ts,
                    notes=r.get("notes"),
                )
            )
        return records

    def resume_session(self, session_id: str) -> Dict[str, Any]:
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
        user_id = events[-1].user_id
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
            "user_id": user_id,
            "exists": True,
            "current_state": current_state,
            "current_step": current_step,
            "answers": [a for a in answers if a is not None],
            "verdicts": [v for v in verdicts if v is not None],
            "question": question,
            "is_terminated": is_terminated,
            "events_count": len(events),
        }

    @property
    def engine_name(self) -> str:
        return "PostgreSQL"


def get_database_store(db_url: Optional[str] = None) -> Any:
    """
    Factory function returning PostgresStore if DATABASE_URL is configured,
    otherwise returning MindMeshStore (SQLite).
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()

    url = db_url or os.getenv("DATABASE_URL")
    if url and (url.startswith("postgresql://") or url.startswith("postgres://")):
        try:
            return PostgresStore(db_url=url)
        except Exception as e:
            print(f"PostgreSQL connection error: {e}. Falling back to SQLite.")
            return MindMeshStore()
    return MindMeshStore()
