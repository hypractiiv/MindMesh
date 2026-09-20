"""
tests/test_notifier.py - Unit tests for MindMesh email notification service and decay intervals.

Verifies:
- Confidence-based review interval calculations (1 to 5) and descriptions.
- Email template rendering with HTML + Plaintext and deep links.
- Simulated delivery mode when SMTP credentials are not configured.
- SMTP delivery mode with smtplib mock.
- Safe zero-crash fallback on network/SMTP error.
- Automated due-review scanning per user account.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from decay import (
    calculate_next_review,
    fast_forward_record,
    get_review_interval_description,
    get_review_interval_hours,
    is_due_for_review,
)
from models import ConceptRecord, Outcome, User
from notifier import (
    NotificationResult,
    ReviewNotifier,
    ReviewSchedulerDaemon,
    default_notifier,
    get_or_start_review_daemon,
)
from store import MindMeshStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_notifier.db"
        store = MindMeshStore(db_path=db_path)
        yield store


def test_confidence_based_decay_intervals():
    """Verify that calculate_next_review scales with student confidence ratings."""
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # First-try correct:
    # 5 -> 7 days
    assert get_review_interval_hours(Outcome.FIRST_TRY_CORRECT, 5) == 168.0
    r5 = calculate_next_review(Outcome.FIRST_TRY_CORRECT, 5, base_time=now)
    assert r5 == now + timedelta(days=7)

    # 4 -> 5 days
    assert get_review_interval_hours(Outcome.FIRST_TRY_CORRECT, 4) == 120.0
    r4 = calculate_next_review(Outcome.FIRST_TRY_CORRECT, 4, base_time=now)
    assert r4 == now + timedelta(days=5)

    # 3 -> 3 days
    assert get_review_interval_hours(Outcome.FIRST_TRY_CORRECT, 3) == 72.0
    r3 = calculate_next_review(Outcome.FIRST_TRY_CORRECT, 3, base_time=now)
    assert r3 == now + timedelta(days=3)

    # 2 -> 2 days
    assert get_review_interval_hours(Outcome.FIRST_TRY_CORRECT, 2) == 48.0
    r2 = calculate_next_review(Outcome.FIRST_TRY_CORRECT, 2, base_time=now)
    assert r2 == now + timedelta(days=2)

    # 1 -> 1 day
    assert get_review_interval_hours(Outcome.FIRST_TRY_CORRECT, 1) == 24.0
    r1 = calculate_next_review(Outcome.FIRST_TRY_CORRECT, 1, base_time=now)
    assert r1 == now + timedelta(days=1)

    # Higher confidence must yield strictly longer retention intervals for first-try correct
    assert r5 > r4 > r3 > r2 > r1

    # Resolved on follow-up:
    # 5 -> 3 days
    assert get_review_interval_hours(Outcome.RESOLVED_ON_FOLLOW_UP, 5) == 72.0
    # 3 -> 2 days (48h)
    assert get_review_interval_hours(Outcome.RESOLVED_ON_FOLLOW_UP, 3) == 48.0
    # 1 -> 1 day
    assert get_review_interval_hours(Outcome.RESOLVED_ON_FOLLOW_UP, 1) == 24.0

    # Unresolved with high confidence (blind spot): 18h
    assert get_review_interval_hours(Outcome.UNRESOLVED, 5) == 18.0
    assert get_review_interval_hours(Outcome.UNRESOLVED, 2) == 24.0

    # Descriptions
    desc5 = get_review_interval_description(Outcome.FIRST_TRY_CORRECT, 5)
    assert "7 days" in desc5
    assert "5/5" in desc5


def test_format_review_email_structure():
    """Verify HTML and plaintext email template generation."""
    notifier = ReviewNotifier(app_url="https://mindmesh.edu")
    subject, text_body, html_body = notifier.format_review_email(
        student_name="Alice",
        concept_id="binary_search_bounds",
        topic_name="Binary Search Bounds",
        outcome=Outcome.FIRST_TRY_CORRECT,
        confidence=5,
    )

    assert "Binary Search Bounds" in subject
    assert "Alice" in text_body
    assert "binary_search_bounds" in text_body
    assert "5/5" in text_body
    assert "https://mindmesh.edu/?topic=binary_search_bounds" in text_body

    assert "<!DOCTYPE html>" in html_body
    assert "Binary Search Bounds" in html_body
    assert "⭐⭐⭐⭐⭐" in html_body
    assert "https://mindmesh.edu/?topic=binary_search_bounds" in html_body
    assert "Active Recall" in html_body


def test_simulated_email_delivery_when_unconfigured():
    """When SMTP is unconfigured, email delivery succeeds in simulated mode without network calls."""
    notifier = ReviewNotifier(smtp_host="")
    assert not notifier.is_live_smtp_enabled()

    res = notifier.send_review_reminder(
        recipient="student@university.edu",
        student_name="Bob",
        concept_id="recursion_base_case",
        confidence=4,
        outcome=Outcome.RESOLVED_ON_FOLLOW_UP,
    )

    assert res.success is True
    assert res.mode == "simulated"
    assert res.recipient == "student@university.edu"
    assert res.concept_id == "recursion_base_case"
    assert res.error is None
    assert "recursion_base_case" in (res.body_text or "")
    assert len(notifier.sent_log) == 1


def test_invalid_email_handling():
    """Invalid recipient emails are caught and reported cleanly."""
    notifier = ReviewNotifier()
    res = notifier.send_review_reminder(
        recipient="not-an-email",
        student_name="Bob",
        concept_id="recursion_base_case",
    )
    assert res.success is False
    assert res.mode == "invalid_email"
    assert "Invalid email" in (res.error or "")


@patch("smtplib.SMTP")
def test_live_smtp_delivery_success(mock_smtp_cls):
    """When SMTP credentials are provided, email is dispatched over SMTP."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    notifier = ReviewNotifier(
        smtp_host="smtp.university.edu",
        smtp_port=587,
        smtp_user="noreply@university.edu",
        smtp_password="app_password_123",
        smtp_from="noreply@university.edu",
        smtp_use_tls=True,
    )
    assert notifier.is_live_smtp_enabled()

    res = notifier.send_review_reminder(
        recipient="student@university.edu",
        student_name="Carol",
        concept_id="graph_bfs",
        confidence=5,
        outcome=Outcome.FIRST_TRY_CORRECT,
    )

    assert res.success is True
    assert res.mode == "smtp"
    assert res.error is None

    # Verify SMTP calls
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("noreply@university.edu", "app_password_123")
    mock_server.sendmail.assert_called_once()
    call_args = mock_server.sendmail.call_args[0]
    assert call_args[0] == "noreply@university.edu"
    assert call_args[1] == ["student@university.edu"]
    assert "graph_bfs" in (res.body_text or "")
    assert "graph_bfs" in (res.body_html or "")
    assert res.concept_id == "graph_bfs"


@patch("smtplib.SMTP")
def test_smtp_network_failure_zero_crash(mock_smtp_cls):
    """Network or authentication failure during SMTP delivery is safely handled without crashing."""
    mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused by host")

    notifier = ReviewNotifier(smtp_host="smtp.invalid.domain")
    res = notifier.send_review_reminder(
        recipient="student@university.edu",
        student_name="Dave",
        concept_id="sql_joins",
    )

    assert res.success is False
    assert res.mode == "smtp"
    assert "Connection refused" in (res.error or "")


def test_notify_due_reviews_for_user(temp_store):
    """Verifies that only overdue reviews trigger notifications for a registered student."""
    now = datetime.now(timezone.utc)
    user = temp_store.create_user("eve", "Eve", "eve123", email="eve@institute.edu")
    assert user is not None

    # Concept 1: Due in the future (not due yet)
    rec_future = ConceptRecord(
        concept_id="future_topic",
        session_id="sess-future",
        user_id="eve",
        confidence=5,
        outcome=Outcome.FIRST_TRY_CORRECT,
        attempts_count=1,
        next_review_at=now + timedelta(days=7),
    )
    temp_store.save_concept_record(rec_future)

    # Concept 2: Due now (overdue)
    rec_due = ConceptRecord(
        concept_id="due_topic",
        session_id="sess-due",
        user_id="eve",
        confidence=3,
        outcome=Outcome.RESOLVED_ON_FOLLOW_UP,
        attempts_count=2,
        next_review_at=now - timedelta(hours=2),
    )
    temp_store.save_concept_record(rec_due)

    notifier = ReviewNotifier()
    results = notifier.notify_due_reviews_for_user(temp_store, user)

    # Only the overdue concept should trigger an email notification
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].concept_id == "due_topic"
    assert results[0].recipient == "eve@institute.edu"


def test_notify_user_without_email_graceful(temp_store):
    """User without an email address is handled gracefully without errors."""
    user_no_email = temp_store.create_user("frank", "Frank", "pass123", email=None)
    assert user_no_email is not None

    notifier = ReviewNotifier()
    results = notifier.notify_due_reviews_for_user(temp_store, user_no_email)

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].mode == "skipped"
    assert "no email" in (results[0].error or "").lower()


def test_configure_smtp_updates_notifier():
    """Verify configure_smtp dynamically updates delivery parameters."""
    notifier = ReviewNotifier(smtp_host="")
    assert not notifier.is_live_smtp_enabled()

    notifier.configure_smtp(
        smtp_host="smtp.sendgrid.net",
        smtp_port=587,
        smtp_user="apikey",
        smtp_password="secret_token",
        smtp_from="system@mindmesh.org",
        smtp_use_tls=True,
    )
    assert notifier.is_live_smtp_enabled()
    assert notifier.smtp_host == "smtp.sendgrid.net"
    assert notifier.smtp_port == 587
    assert notifier.smtp_user == "apikey"
    assert notifier.smtp_from == "system@mindmesh.org"


def test_review_scheduler_daemon_lifecycle_and_dispatch(temp_store):
    """Verify ReviewSchedulerDaemon checks store, dispatches overdue reviews, and prevents duplicate alerts."""
    now = datetime.now(timezone.utc)
    user = temp_store.create_user("grace", "Grace", "grace123", email="grace@example.edu")
    assert user is not None

    rec_due = ConceptRecord(
        concept_id="dynamic_programming_knapsack",
        session_id="sess-grace-1",
        user_id="grace",
        confidence=2,
        outcome=Outcome.RESOLVED_ON_FOLLOW_UP,
        attempts_count=2,
        next_review_at=now - timedelta(hours=1),
    )
    temp_store.save_concept_record(rec_due)

    notifier = ReviewNotifier(smtp_host="")
    daemon = ReviewSchedulerDaemon(store=temp_store, notifier=notifier, check_interval_seconds=60)

    # First check pass should find 1 due review and send 1 simulated reminder
    dispatched_count = daemon.check_now()
    assert dispatched_count == 1
    assert len(notifier.sent_log) == 1
    assert notifier.sent_log[0].concept_id == "dynamic_programming_knapsack"
    assert notifier.sent_log[0].recipient == "grace@example.edu"

    # Second check pass immediately after should NOT send duplicate email
    duplicate_count = daemon.check_now()
    assert duplicate_count == 0
    assert len(notifier.sent_log) == 1
