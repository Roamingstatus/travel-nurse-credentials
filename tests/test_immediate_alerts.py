"""Tests for immediate expired-document alert delivery.

Scenarios covered:
  1. Free user — no alert sent
  2. Premium, email_enabled=False — no alert sent
  3. Premium, email_enabled=True, doc not expired — no alert sent
  4. Premium, email_enabled=True, doc expired — email sent and logged
  5. Premium+, both enabled — email + SMS sent and logged
  6. Duplicate prevention — second call is skipped (already sent)
  7. Provider failure — log entry recorded with status="failed"
  8. get_expired_alert_statuses — returns correct status dict
  9. Scheduler sweep — expired doc picked up by daily job
"""
from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Document, ReminderLog, ReminderSettings, User

_counter = itertools.count(1)

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
Base.metadata.create_all(_ENGINE)
_Session = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(db, tier="premium", email_enabled=True, sms_enabled=False, phone=None):
    n = next(_counter)
    u = User(
        google_sub=f"sub-{n}",
        email=f"user{n}@example.com",
        name=f"User {n}",
        subscription_tier=tier,
    )
    db.add(u)
    db.flush()
    s = ReminderSettings(
        user_id=u.id,
        email_enabled=email_enabled,
        sms_enabled=sms_enabled,
        phone_number=phone,
    )
    db.add(s)
    db.commit()
    db.refresh(u)
    return u


def _doc(db, user, *, expired=True, has_expiry=True):
    n = next(_counter)
    if not has_expiry:
        exp = None
    elif expired:
        exp = datetime.utcnow() - timedelta(days=5)
    else:
        exp = datetime.utcnow() + timedelta(days=30)
    doc = Document(
        user_id=user.id,
        title=f"Doc {n}",
        category="Certifications",
        stored_filename=f"doc{n}.pdf",
        original_filename=f"doc{n}.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        expires_at=exp,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _ok_email():
    return {"ok": True, "message_id": "em-123"}


def _ok_sms():
    return {"ok": True, "message_id": "sm-456"}


def _fail():
    return {"ok": False, "error": "provider_error"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_free_user_no_alert():
    """Free users never receive expired-document alerts."""
    db = _Session()
    try:
        user = _user(db, tier="free", email_enabled=True)
        doc = _doc(db, user, expired=True)
        with (
            patch("app.services.email_service.send_expired_document_email") as mock_email,
            patch("app.services.sms_service.send_expired_document_sms") as mock_sms,
        ):
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"] is None
        assert result["sms"] is None
        mock_email.assert_not_called()
        mock_sms.assert_not_called()
        assert db.query(ReminderLog).filter_by(document_id=doc.id, trigger_type="immediate_expired").count() == 0
    finally:
        db.close()


def test_premium_email_disabled_no_alert():
    """Premium user with email_enabled=False receives no email."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=False)
        doc = _doc(db, user, expired=True)
        with patch("app.services.email_service.send_expired_document_email") as mock_email:
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"] is None
        mock_email.assert_not_called()
    finally:
        db.close()


def test_not_expired_no_alert():
    """Document that hasn't expired yet does not trigger an alert."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, expired=False)
        with patch("app.services.email_service.send_expired_document_email") as mock_email:
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"] is None
        mock_email.assert_not_called()
    finally:
        db.close()


def test_no_expiry_no_alert():
    """Document without an expiry date does not trigger an alert."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, has_expiry=False)
        with patch("app.services.email_service.send_expired_document_email") as mock_email:
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"] is None
        mock_email.assert_not_called()
    finally:
        db.close()


def test_premium_expired_doc_sends_email():
    """Premium user with email enabled gets an email for an expired doc."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, expired=True)
        with (
            patch("app.services.email_service.send_expired_document_email", return_value=_ok_email()) as mock_email,
            patch("app.events.log_event"),
        ):
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"]["ok"] is True
        assert result["sms"] is None
        mock_email.assert_called_once()
        log = db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="email"
        ).one()
        assert log.status == "sent"
        assert log.days_before == 0
    finally:
        db.close()


def test_premium_plus_expired_doc_sends_email_and_sms():
    """Premium+ user with both channels enabled gets email and SMS."""
    db = _Session()
    try:
        user = _user(db, tier="premium_plus", email_enabled=True, sms_enabled=True, phone="+15550001111")
        doc = _doc(db, user, expired=True)
        with (
            patch("app.services.email_service.send_expired_document_email", return_value=_ok_email()),
            patch("app.services.sms_service.send_expired_document_sms", return_value=_ok_sms()),
            patch("app.events.log_event"),
        ):
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"]["ok"] is True
        assert result["sms"]["ok"] is True
        email_log = db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="email"
        ).one()
        sms_log = db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="sms"
        ).one()
        assert email_log.status == "sent"
        assert sms_log.status == "sent"
    finally:
        db.close()


def test_duplicate_prevention_email():
    """A second call for the same doc/user/channel is skipped."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, expired=True)
        with (
            patch("app.services.email_service.send_expired_document_email", return_value=_ok_email()),
            patch("app.events.log_event"),
        ):
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result1 = check_and_send_immediate_expired_alert(user, doc, db)
        assert result1["email"]["ok"] is True

        with patch("app.services.email_service.send_expired_document_email") as mock2:
            result2 = check_and_send_immediate_expired_alert(user, doc, db)
        mock2.assert_not_called()
        assert result2["email"]["duplicate"] is True
        assert db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="email"
        ).count() == 1
    finally:
        db.close()


def test_provider_failure_logged():
    """A provider error is recorded in reminder_logs with status=failed."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, expired=True)
        with (
            patch("app.services.email_service.send_expired_document_email", return_value=_fail()),
            patch("app.events.log_event"),
        ):
            from app.services.immediate_alerts import check_and_send_immediate_expired_alert
            result = check_and_send_immediate_expired_alert(user, doc, db)
        assert result["email"]["ok"] is False
        log = db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="email"
        ).one()
        assert log.status == "failed"
        assert log.error_message == "provider_error"
    finally:
        db.close()


def test_get_expired_alert_statuses():
    """get_expired_alert_statuses returns correct {doc_id: {channel: status}} dict."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc1 = _doc(db, user, expired=True)
        doc2 = _doc(db, user, expired=True)
        doc3 = _doc(db, user, expired=True)

        # Write logs manually
        db.add(ReminderLog(
            user_id=user.id, document_id=doc1.id,
            reminder_type="email", trigger_type="immediate_expired",
            days_before=0, sent_at=datetime.utcnow(), status="sent",
        ))
        db.add(ReminderLog(
            user_id=user.id, document_id=doc2.id,
            reminder_type="email", trigger_type="immediate_expired",
            days_before=0, sent_at=datetime.utcnow(), status="failed",
        ))
        db.commit()

        from app.services.immediate_alerts import get_expired_alert_statuses
        statuses = get_expired_alert_statuses(db, user.id, [doc1.id, doc2.id, doc3.id])

        assert statuses[doc1.id]["email"] == "sent"
        assert statuses[doc2.id]["email"] == "failed"
        assert doc3.id not in statuses
    finally:
        db.close()


def test_scheduler_sweep_sends_immediate_alerts():
    """Daily scheduler sweep picks up expired docs and fires immediate alerts."""
    db = _Session()
    try:
        user = _user(db, tier="premium", email_enabled=True)
        doc = _doc(db, user, expired=True)

        with (
            patch("app.services.email_service.send_expired_document_email", return_value=_ok_email()),
            patch("app.events.log_event"),
            patch("app.db.SessionLocal", return_value=db),
        ):
            import app.services.reminder_scheduler as sched
            orig_close = db.close
            db.close = lambda: None
            sched.check_expiring_documents()
            db.close = orig_close

        assert db.query(ReminderLog).filter_by(
            document_id=doc.id, trigger_type="immediate_expired", reminder_type="email"
        ).count() == 1
    finally:
        db.close()
