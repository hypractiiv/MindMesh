"""
notifier.py - Spaced repetition email notification service for MindMesh.

Owns:
- Responsive HTML & plaintext email templates tailored for spaced repetition retention.
- SMTP dispatch with STARTTLS and robust error handling.
- Simulated zero-crash delivery mode when SMTP credentials are unconfigured.
- Automated check and dispatch for overdue spaced-repetition concepts based on confidence intervals.
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from decay import get_review_interval_description, is_due_for_review
from models import ConceptRecord, Outcome, User

logger = logging.getLogger(__name__)


class NotificationResult(BaseModel):
    """Execution status and metadata for an email dispatch."""
    success: bool
    recipient: str
    subject: str
    mode: str = "simulated"  # "smtp" or "simulated"
    error: Optional[str] = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    concept_id: Optional[str] = None
    topic_name: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None


class ReviewNotifier:
    """Manages spaced repetition email notifications via SMTP or safe simulated mode."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        smtp_use_tls: Optional[bool] = None,
        app_url: Optional[str] = None,
    ):
        self.smtp_host = (
            smtp_host if smtp_host is not None else os.getenv("SMTP_HOST", "")
        ).strip()
        self.smtp_port = int(
            smtp_port if smtp_port is not None else os.getenv("SMTP_PORT", "587")
        )
        self.smtp_user = (
            smtp_user if smtp_user is not None else os.getenv("SMTP_USER", "")
        ).strip()
        self.smtp_password = (
            smtp_password if smtp_password is not None else os.getenv("SMTP_PASSWORD", "")
        ).strip()
        self.smtp_from = (
            smtp_from
            if smtp_from is not None
            else os.getenv("SMTP_FROM", "notifications@mindmesh.local")
        ).strip()

        env_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
        self.smtp_use_tls = smtp_use_tls if smtp_use_tls is not None else env_tls
        self.app_url = (
            app_url if app_url is not None else os.getenv("APP_URL", "http://localhost:8501")
        ).rstrip("/")

        # In-memory delivery history for auditing, tests, and UI feedback
        self.sent_log: List[NotificationResult] = []

    def configure_smtp(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        smtp_from: str = "",
        smtp_use_tls: bool = True,
        app_url: Optional[str] = None,
    ) -> None:
        """Updates SMTP credentials and delivery configuration dynamically at runtime."""
        self.smtp_host = smtp_host.strip()
        self.smtp_port = int(smtp_port)
        self.smtp_user = smtp_user.strip()
        self.smtp_password = smtp_password.strip()
        self.smtp_from = smtp_from.strip() or (smtp_user.strip() if smtp_user else "notifications@mindmesh.local")
        self.smtp_use_tls = smtp_use_tls
        if app_url:
            self.app_url = app_url.rstrip("/")

    def is_live_smtp_enabled(self) -> bool:
        """Returns True if SMTP host is configured for live network delivery."""
        return bool(self.smtp_host)

    def format_review_email(
        self,
        student_name: str,
        concept_id: str,
        topic_name: Optional[str] = None,
        outcome: Optional[Outcome | str] = None,
        confidence: Optional[int] = None,
        next_review_at: Optional[datetime] = None,
        app_url: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """
        Builds (subject, plain_text, html_body) for a spaced repetition review reminder.
        Matches MindMesh's Obsidian/Indigo dark design system.
        """
        clean_topic = topic_name or concept_id.replace("_", " ").title()
        conf_val = confidence if confidence is not None else 3
        outcome_val = outcome.value if isinstance(outcome, Outcome) else (str(outcome) if outcome else "review_due")
        target_url = f"{(app_url or self.app_url)}/?topic={concept_id}"

        # Star rating display
        stars = "⭐" * conf_val + "☆" * (5 - conf_val)

        # Interval reasoning
        interval_desc = "Optimal review window reached"
        if isinstance(outcome, Outcome):
            interval_desc = get_review_interval_description(outcome, conf_val)
        elif outcome_val == "first_try_correct":
            interval_desc = get_review_interval_description(Outcome.FIRST_TRY_CORRECT, conf_val)
        elif outcome_val == "resolved_on_follow_up":
            interval_desc = get_review_interval_description(Outcome.RESOLVED_ON_FOLLOW_UP, conf_val)

        subject = f"🧠 MindMesh Review Due: {clean_topic}"

        # Plain Text Body
        text_body = f"""Hello {student_name},

It's time to consolidate your memory for "{clean_topic}" in MindMesh!

Spaced Repetition Review Details:
- Target Concept: {clean_topic} ({concept_id})
- Last Recorded Confidence: {conf_val}/5 ({stars})
- Last Outcome: {outcome_val}
- Retention Calculation: {interval_desc}

Practicing now prevents memory decay and locks in conceptual mastery.

Reinforce this concept now:
{target_url}

-- 
MindMesh Active Recall & Spaced Repetition Engine
"""

        # HTML Body (Dark theme: #0A0E17, #6366F1, #10B981)
        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0A0E17; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #F8FAFC;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0A0E17; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #111827; border: 1px solid #1E293B; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);">
          <!-- Header -->
          <tr>
            <td style="padding: 28px 32px; background: linear-gradient(135deg, #1E1B4B 0%, #0F172A 100%); border-bottom: 1px solid #312E81;">
              <table role="presentation" width="100%">
                <tr>
                  <td>
                    <span style="font-size: 28px; vertical-align: middle;">🧠</span>
                    <span style="font-size: 22px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px; margin-left: 8px;">Mind<span style="color: #818CF8;">Mesh</span></span>
                  </td>
                  <td align="right">
                    <span style="background: rgba(99, 102, 241, 0.2); color: #A5B4FC; font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 4px 10px; border-radius: 20px; border: 1px solid rgba(99, 102, 241, 0.4);">
                      Spaced Repetition
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 32px;">
              <h2 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #F8FAFC;">
                Time to Reinforce: <span style="color: #818CF8;">{clean_topic}</span>
              </h2>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #94A3B8;">
                Hi <strong style="color: #E2E8F0;">{student_name}</strong>, according to your confidence decay curve, this concept is due for active retrieval practice to achieve permanent long-term retention.
              </p>

              <!-- Metrics Card -->
              <table role="presentation" width="100%" style="background-color: #0B0F19; border: 1px solid #1F2937; border-radius: 10px; padding: 18px; margin-bottom: 26px;">
                <tr>
                  <td style="padding: 6px 0; font-size: 13px; color: #94A3B8;">Target Concept:</td>
                  <td align="right" style="padding: 6px 0; font-size: 13px; font-weight: 600; color: #F8FAFC;">{clean_topic}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 0; font-size: 13px; color: #94A3B8;">Prior Confidence:</td>
                  <td align="right" style="padding: 6px 0; font-size: 13px; font-weight: 600; color: #FBBF24;">{conf_val}/5 {stars}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 0; font-size: 13px; color: #94A3B8;">Last Outcome:</td>
                  <td align="right" style="padding: 6px 0; font-size: 13px; font-weight: 600; color: #34D399;">{outcome_val}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 0; font-size: 13px; color: #94A3B8;">Optimal Interval:</td>
                  <td align="right" style="padding: 6px 0; font-size: 12px; color: #818CF8;">{interval_desc}</td>
                </tr>
              </table>

              <!-- Call to Action Button -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                <tr>
                  <td align="center">
                    <a href="{target_url}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: #FFFFFF; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 32px; border-radius: 8px; box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);">
                      🎯 Reinforce Concept Now &rarr;
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #64748B; text-align: center;">
                Active retrieval strengthens neural pathways and prevents the forgetting curve from taking hold.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #0B0F19; border-top: 1px solid #1E293B; text-align: center;">
              <p style="margin: 0; font-size: 11px; color: #64748B;">
                Sent by <strong>MindMesh Active Recall System</strong> for {student_name}.
                <br>Automated review notifications based on your self-rated confidence levels.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        return subject, text_body, html_body

    def send_review_reminder(
        self,
        recipient: str,
        student_name: str,
        concept_id: str,
        topic_name: Optional[str] = None,
        outcome: Optional[Outcome | str] = None,
        confidence: Optional[int] = None,
        next_review_at: Optional[datetime] = None,
        app_url: Optional[str] = None,
    ) -> NotificationResult:
        """
        Dispatches a spaced repetition review reminder to the student.
        Uses SMTP if host is configured, otherwise simulates safe delivery.
        """
        clean_recipient = recipient.strip()
        if not clean_recipient or "@" not in clean_recipient:
            result = NotificationResult(
                success=False,
                recipient=recipient,
                subject="",
                mode="invalid_email",
                error="Invalid email address format.",
                concept_id=concept_id,
            )
            self.sent_log.append(result)
            return result

        subject, text_body, html_body = self.format_review_email(
            student_name=student_name,
            concept_id=concept_id,
            topic_name=topic_name,
            outcome=outcome,
            confidence=confidence,
            next_review_at=next_review_at,
            app_url=app_url,
        )

        clean_topic = topic_name or concept_id.replace("_", " ").title()

        # Simulated Delivery Mode (Default when no SMTP server is configured)
        if not self.is_live_smtp_enabled():
            logger.info(
                "Simulated email sent to %s for concept '%s' (SMTP_HOST unset).",
                clean_recipient,
                concept_id,
            )
            result = NotificationResult(
                success=True,
                recipient=clean_recipient,
                subject=subject,
                mode="simulated",
                concept_id=concept_id,
                topic_name=clean_topic,
                body_text=text_body,
                body_html=html_body,
            )
            self.sent_log.append(result)
            return result

        # Live SMTP Delivery Mode
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = clean_recipient

        part1 = MIMEText(text_body, "plain", "utf-8")
        part2 = MIMEText(html_body, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                if self.smtp_use_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, [clean_recipient], msg.as_string())

            logger.info("SMTP email successfully delivered to %s for '%s'.", clean_recipient, concept_id)
            result = NotificationResult(
                success=True,
                recipient=clean_recipient,
                subject=subject,
                mode="smtp",
                concept_id=concept_id,
                topic_name=clean_topic,
                body_text=text_body,
                body_html=html_body,
            )
            self.sent_log.append(result)
            return result

        except Exception as exc:
            err_msg = f"SMTP error during delivery to {clean_recipient}: {exc}"
            logger.warning("%s. Recording failed delivery.", err_msg)
            result = NotificationResult(
                success=False,
                recipient=clean_recipient,
                subject=subject,
                mode="smtp",
                error=str(exc),
                concept_id=concept_id,
                topic_name=clean_topic,
                body_text=text_body,
                body_html=html_body,
            )
            self.sent_log.append(result)
            return result

    def notify_due_reviews_for_user(
        self,
        store: Any,
        user: User,
        app_url: Optional[str] = None,
    ) -> List[NotificationResult]:
        """
        Queries all concept records for user, filters by is_due_for_review,
        and sends review reminders for every due concept to the user's email.
        """
        if not user.email:
            logger.info("User '%s' has no email registered. Skipping notifications.", user.username)
            return [
                NotificationResult(
                    success=False,
                    recipient="",
                    subject="No email registered",
                    mode="skipped",
                    error=f"Student profile '@{user.username}' has no email configured.",
                )
            ]

        records = store.get_user_records(user.username)
        due_records = [r for r in records if is_due_for_review(r)]

        results: List[NotificationResult] = []
        for rec in due_records:
            res = self.send_review_reminder(
                recipient=user.email,
                student_name=user.display_name,
                concept_id=rec.concept_id,
                outcome=rec.outcome,
                confidence=rec.confidence,
                next_review_at=rec.next_review_at,
                app_url=app_url,
            )
            results.append(res)

        return results

    def check_all_due_and_notify(
        self,
        store: Any,
        app_url: Optional[str] = None,
    ) -> Dict[str, List[NotificationResult]]:
        """
        Checks all registered students in the store and sends notifications for due concepts.
        """
        users = store.list_users()
        summary: Dict[str, List[NotificationResult]] = {}
        for u in users:
            if u.email:
                summary[u.username] = self.notify_due_reviews_for_user(store, u, app_url=app_url)
        return summary


# Global singleton instance for easy import across Streamlit & CLI
default_notifier = ReviewNotifier()


class ReviewSchedulerDaemon:
    """
    Background daemon thread that periodically monitors the database store
    for any student concepts reaching their scheduled review time,
    and automatically dispatches review reminder emails.
    """

    def __init__(
        self,
        store: Any,
        notifier: ReviewNotifier,
        check_interval_seconds: int = 30,
    ):
        self.store = store
        self.notifier = notifier
        self.check_interval = check_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check_at: Optional[datetime] = None
        self._dispatched_records: set[tuple[str, str, str]] = set()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_check_at(self) -> Optional[datetime]:
        return self._last_check_at

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MindMeshReviewDaemon")
        self._thread.start()
        logger.info("ReviewSchedulerDaemon started (interval: %ds).", self.check_interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("ReviewSchedulerDaemon stopped.")

    def check_now(self) -> int:
        """Performs an immediate pass to check and notify due reviews. Returns count of dispatched emails."""
        self._last_check_at = datetime.now(timezone.utc)
        count = 0
        try:
            users = self.store.list_users()
        except Exception as exc:
            logger.warning("ReviewSchedulerDaemon failed to list users: %s", exc)
            return 0

        for user in users:
            if not getattr(user, "email", None):
                continue
            try:
                records = self.store.get_user_records(user.username)
            except Exception as exc:
                logger.warning("ReviewSchedulerDaemon failed to get records for %s: %s", user.username, exc)
                continue

            for rec in records:
                if is_due_for_review(rec):
                    review_iso = rec.next_review_at.isoformat() if rec.next_review_at else "none"
                    record_key = (user.username, rec.concept_id, review_iso)
                    if record_key not in self._dispatched_records:
                        self.notifier.send_review_reminder(
                            recipient=user.email,
                            student_name=user.display_name,
                            concept_id=rec.concept_id,
                            outcome=rec.outcome,
                            confidence=rec.confidence,
                            next_review_at=rec.next_review_at,
                        )
                        self._dispatched_records.add(record_key)
                        count += 1
        return count

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_now()
            except Exception as exc:
                logger.error("Unexpected error in ReviewSchedulerDaemon: %s", exc)
            self._stop_event.wait(self.check_interval)


_global_daemon: Optional[ReviewSchedulerDaemon] = None


def get_or_start_review_daemon(
    store: Any,
    notifier: Optional[ReviewNotifier] = None,
    interval_seconds: int = 30,
) -> ReviewSchedulerDaemon:
    """Returns or starts the global ReviewSchedulerDaemon background thread."""
    global _global_daemon
    if _global_daemon is None:
        _global_daemon = ReviewSchedulerDaemon(
            store=store,
            notifier=notifier or default_notifier,
            check_interval_seconds=interval_seconds,
        )
    if not _global_daemon.is_running:
        _global_daemon.start()
    return _global_daemon

