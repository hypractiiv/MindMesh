from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SessionState:
    session_id: str
    concept: str
    question: str
    state: str
    attempt: int


class Store:
    def __init__(self, db_path: str | Path = "mindmesh.db") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                concept TEXT NOT NULL,
                question TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                concept TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_session(
        self,
        *,
        session_id: str,
        concept: str,
        question: str,
        state: str,
        attempt: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO sessions (session_id, concept, question, state, attempt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, concept, question, state, attempt, now, now),
        )
        self.conn.commit()

    def update_session(self, session_id: str, *, state: str | None = None, attempt: int | None = None) -> None:
        current = self.get_session(session_id)
        if not current:
            raise KeyError(f"Unknown session_id: {session_id}")
        next_state = state if state is not None else current.state
        next_attempt = attempt if attempt is not None else current.attempt
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE sessions SET state = ?, attempt = ?, updated_at = ? WHERE session_id = ?
            """,
            (next_state, next_attempt, now, session_id),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> SessionState | None:
        row = self.conn.execute(
            "SELECT session_id, concept, question, state, attempt FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return SessionState(
            session_id=row["session_id"],
            concept=row["concept"],
            question=row["question"],
            state=row["state"],
            attempt=row["attempt"],
        )

    def append_record(self, *, session_id: str, concept: str, kind: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO records (session_id, concept, kind, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, concept, kind, json.dumps(payload), now),
        )
        self.conn.commit()

    def get_records(self, *, session_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is None:
            rows = self.conn.execute(
                "SELECT kind, payload, created_at FROM records WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT kind, payload, created_at FROM records WHERE session_id = ? AND kind = ? ORDER BY id ASC",
                (session_id, kind),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"])
            payload["kind"] = row["kind"]
            payload["created_at"] = row["created_at"]
            out.append(payload)
        return out

    def get_latest_record(self, *, session_id: str, kind: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT kind, payload, created_at
            FROM records
            WHERE session_id = ? AND kind = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, kind),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload["kind"] = row["kind"]
        payload["created_at"] = row["created_at"]
        return payload

    def close(self) -> None:
        self.conn.close()
