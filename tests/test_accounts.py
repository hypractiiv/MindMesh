"""
tests/test_accounts.py - Verification of multi-user account management and student data isolation.

Verifies:
- User registration with salted password hashing.
- Credential authentication (success and rejection).
- Student data isolation across multiple users studying the same concept.
- Session crash recovery preserving student identity.
"""

import tempfile
from pathlib import Path
import pytest

from flow import FlowSession
from models import Outcome, State
from steps import step_answering, step_checking, step_followup, step_prompting
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_accounts.db"
        yield MindMeshStore(db_path=db_path)


def test_user_registration_and_authentication(temp_store):
    """Test user creation, duplicate prevention, and password hashing authentication."""
    # 1. Register Alice
    alice = temp_store.create_user(username="alice", display_name="Alice Smith", password="secure_password_123")
    assert alice is not None
    assert alice.username == "alice"
    assert alice.display_name == "Alice Smith"

    # 2. Duplicate username rejected
    dup = temp_store.create_user(username="alice", display_name="Alice 2", password="other_password")
    assert dup is None

    # 3. Successful authentication
    auth_alice = temp_store.authenticate_user("alice", "secure_password_123")
    assert auth_alice is not None
    assert auth_alice.username == "alice"

    # 4. Failed authentication with wrong password
    bad_auth = temp_store.authenticate_user("alice", "wrong_password")
    assert bad_auth is None

    # 5. Nonexistent user authentication
    unknown_auth = temp_store.authenticate_user("charlie", "any_password")
    assert unknown_auth is None


def test_student_data_isolation_same_concept(temp_store):
    """
    Verify complete isolation between two students studying the same concept:
    - Alice answers correctly on first try (confidence 5, first_try_correct).
    - Bob answers wrong initially (mismatch), then resolves on follow-up (confidence 3).
    - Their histories and next-review dates must not collide or overwrite.
    """
    temp_store.create_user("alice", "Alice", "alice123")
    temp_store.create_user("bob", "Bob", "bob123")

    concept = "recursion_base_case"

    # --- Alice's Session ---
    s_alice = FlowSession(session_id="alice-sess-1", store=temp_store, user_id="alice")
    step_prompting(s_alice, topic=concept)
    step_answering(s_alice, "if not numbers: return 0", self_rating=5)
    step_checking(s_alice)
    assert s_alice.state == State.RECORDED

    # --- Bob's Session ---
    s_bob = FlowSession(session_id="bob-sess-1", store=temp_store, user_id="bob")
    step_prompting(s_bob, topic=concept)
    step_answering(s_bob, "if len(numbers) == 0: return 1", self_rating=4)
    step_checking(s_bob)
    assert s_bob.state == State.WAITING_FOR_FOLLOWUP

    step_followup(s_bob, "if not numbers: return 0")
    step_checking(s_bob)
    assert s_bob.state == State.RECORDED

    # --- Verification of Isolation ---
    alice_records = temp_store.get_concept_records(concept, user_id="alice")
    bob_records = temp_store.get_concept_records(concept, user_id="bob")

    assert len(alice_records) == 1
    assert alice_records[0].user_id == "alice"
    assert alice_records[0].outcome == Outcome.FIRST_TRY_CORRECT
    assert alice_records[0].confidence == 5

    assert len(bob_records) == 1
    assert bob_records[0].user_id == "bob"
    assert bob_records[0].outcome == Outcome.RESOLVED_ON_FOLLOW_UP
    assert bob_records[0].confidence == 3

    # Alice's review date should be +7 days, Bob's should be +2 days
    assert alice_records[0].next_review_at > bob_records[0].next_review_at

    # Check Alice's next encounter receives Alice's history, not Bob's
    s_alice_2 = FlowSession(session_id="alice-sess-2", store=temp_store, user_id="alice")
    step_prompting(s_alice_2, topic=concept)
    events_alice = temp_store.get_session_events("alice-sess-2")
    prior_alice = events_alice[0].payload.get("prior_history")
    assert prior_alice is not None
    assert prior_alice["last_outcome"] == "first_try_correct"
    assert prior_alice["last_confidence"] == 5


def test_session_recovery_preserves_user_id(temp_store):
    """Verify that recovering an interrupted session restores the correct student ID."""
    session_id = "interrupted-user-session"
    s1 = FlowSession(session_id=session_id, store=temp_store, user_id="student_charlie")
    step_prompting(s1, topic="recursion_base_case")
    step_answering(s1, "if len(numbers) == 0: return 1", self_rating=4)
    step_checking(s1)
    assert s1.state == State.WAITING_FOR_FOLLOWUP

    # Process exit simulation
    del s1

    # Resume
    resumed = FlowSession.resume(session_id=session_id, store=temp_store)
    assert resumed.user_id == "student_charlie"
    assert resumed.state == State.WAITING_FOR_FOLLOWUP

    step_followup(resumed, "if not numbers: return 0")
    step_checking(resumed)
    assert resumed.state == State.RECORDED

    rec = temp_store.get_latest_concept_record("recursion_base_case", user_id="student_charlie")
    assert rec is not None
    assert rec.user_id == "student_charlie"
