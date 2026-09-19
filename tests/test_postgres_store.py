"""
tests/test_postgres_store.py - Unit and integration tests for PostgreSQL persistence.

Verifies:
- Interface parity between MindMeshStore and PostgresStore.
- Graceful SQLite fallback when DATABASE_URL is unset or unreachable.
- SQL DDL, queries, UPSERT semantics, and event reconstruction with psycopg2 mocking.
- User management and password hashing in PostgresStore.
"""

import inspect
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from models import ConceptRecord, Outcome, State, User
from store import MindMeshStore, PostgresStore, get_database_store


def test_store_interface_parity():
    """Ensures MindMeshStore and PostgresStore expose the identical public persistence API."""
    expected_methods = [
        "init_db",
        "append_event",
        "get_session_events",
        "save_concept_record",
        "get_concept_records",
        "get_latest_concept_record",
        "get_user_records",
        "resume_session",
        "create_user",
        "authenticate_user",
        "get_user",
    ]

    for method_name in expected_methods:
        assert hasattr(MindMeshStore, method_name), f"MindMeshStore missing {method_name}"
        assert hasattr(PostgresStore, method_name), f"PostgresStore missing {method_name}"

        sig_sqlite = inspect.signature(getattr(MindMeshStore, method_name))
        sig_pg = inspect.signature(getattr(PostgresStore, method_name))

        # Both should take the same parameter names (excluding self)
        assert list(sig_sqlite.parameters.keys()) == list(sig_pg.parameters.keys()), (
            f"Signature mismatch for {method_name}: {sig_sqlite} vs {sig_pg}"
        )

    # Engine name property check
    sqlite_store = MindMeshStore.__new__(MindMeshStore)
    assert sqlite_store.engine_name == "SQLite"

    pg_store = PostgresStore.__new__(PostgresStore)
    assert pg_store.engine_name == "PostgreSQL"


def test_factory_fallback_when_unset(monkeypatch):
    """When DATABASE_URL is unset, get_database_store falls back to SQLite."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = get_database_store(db_url=None)
    assert isinstance(store, MindMeshStore)
    assert store.engine_name == "SQLite"


def test_factory_fallback_on_unreachable_postgres():
    """When a PostgreSQL URL is provided but the host/port is down, falls back to SQLite gracefully."""
    # Using non-routable / closed loopback port
    dead_url = "postgresql://mindmesh:fake_pass@127.0.0.1:54399/fake_db"
    store = get_database_store(db_url=dead_url)
    assert isinstance(store, MindMeshStore)
    assert store.engine_name == "SQLite"


def test_postgres_store_requires_url(monkeypatch):
    """PostgresStore without a db_url or DATABASE_URL env var raises ValueError."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL must be provided"):
        PostgresStore(db_url=None)


@patch("psycopg2.connect")
def test_postgres_init_db_ddl(mock_connect):
    """Verifies PostgresStore executes the full PostgreSQL DDL on init."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    store = PostgresStore(db_url="postgresql://user:pass@localhost:5432/mindmesh")

    # Verify connection was opened and commit called
    assert mock_connect.called
    assert mock_conn.commit.called

    # Check that DDL queries contain proper Postgres types
    executed_statements = [call[0][0] for call in mock_cursor.execute.call_args_list]
    combined_ddl = " ".join(executed_statements)

    assert "CREATE TABLE IF NOT EXISTS users" in combined_ddl
    assert "VARCHAR(50) PRIMARY KEY" in combined_ddl
    assert "CREATE TABLE IF NOT EXISTS session_events" in combined_ddl
    assert "SERIAL PRIMARY KEY" in combined_ddl
    assert "payload_json JSONB NOT NULL" in combined_ddl
    assert "CREATE TABLE IF NOT EXISTS concept_records" in combined_ddl
    assert "VARCHAR(100) NOT NULL UNIQUE" in combined_ddl
    assert "CREATE INDEX IF NOT EXISTS idx_session_events_session_id" in combined_ddl


@patch("psycopg2.connect")
def test_postgres_user_lifecycle(mock_connect):
    """Verifies user creation, password hashing, and authentication against Postgres."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    mock_cursor.rowcount = 1
    mock_cursor.fetchone.return_value = None

    store = PostgresStore(db_url="postgresql://user:pass@localhost:5432/mindmesh")

    # 1. Create user
    user = store.create_user("alice", "Alice Wonder", "s3cretpass")
    assert user is not None
    assert user.username == "alice"
    assert user.display_name == "Alice Wonder"

    # 2. Authenticate user
    salt = "testsalt12345678"
    p_hash = store._hash_password("s3cretpass", salt)

    mock_cursor.fetchone.return_value = {
        "username": "alice",
        "display_name": "Alice Wonder",
        "password_hash": p_hash,
        "salt": salt,
        "created_at": datetime.now(timezone.utc),
    }

    authenticated = store.authenticate_user("alice", "s3cretpass")
    assert authenticated is not None
    assert authenticated.username == "alice"

    # Wrong password fails
    failed = store.authenticate_user("alice", "wrongpass")
    assert failed is None


@patch("psycopg2.connect")
def test_postgres_append_event_and_resume(mock_connect):
    """Verifies Postgres event appending and session state resumption."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    store = PostgresStore(db_url="postgresql://user:pass@localhost:5432/mindmesh")

    # Append event
    store.append_event(
        session_id="pg-session-1",
        step=1,
        state=State.PROMPTING,
        event_type="QUESTION_LOADED",
        payload={"concept": "recursion_base_case", "question": {"id": "q1"}},
        user_id="alice",
    )
    assert mock_cursor.execute.called

    # Mock rows for resumption
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "session_id": "pg-session-1",
            "user_id": "alice",
            "step": 1,
            "state": State.PROMPTING.value,
            "event_type": "QUESTION_LOADED",
            "payload_json": {"concept": "recursion_base_case", "question": {"id": "q1"}},
            "timestamp": datetime.now(timezone.utc),
        },
        {
            "id": 2,
            "session_id": "pg-session-1",
            "user_id": "alice",
            "step": 2,
            "state": State.ANSWERING.value,
            "event_type": "ANSWER_SUBMITTED",
            "payload_json": {"answer": "return 0", "rating": 5},
            "timestamp": datetime.now(timezone.utc),
        },
        {
            "id": 3,
            "session_id": "pg-session-1",
            "user_id": "alice",
            "step": 3,
            "state": State.RECORDED.value,
            "event_type": "RECORD_SAVED",
            "payload_json": {"verdict": {"passed": True}},
            "timestamp": datetime.now(timezone.utc),
        },
    ]

    resumed = store.resume_session("pg-session-1")
    assert resumed["exists"] is True
    assert resumed["user_id"] == "alice"
    assert resumed["current_state"] == State.RECORDED
    assert resumed["is_terminated"] is True
    assert resumed["current_step"] == 3
    assert len(resumed["answers"]) == 1
    assert resumed["answers"][0] == "return 0"
