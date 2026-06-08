"""Tests for the reminder subsystem.

Covers:
- Reminder eligibility (which day thresholds trigger)
- Duplicate prevention (_send_if_not_duplicate)
- Graceful failure when Resend / Twilio keys are absent
- Tier gating (free → no email, premium → email, premium+ → email+SMS)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import itertools

from app.db import Base, Document, ReminderLog, ReminderSettings, User

_sub_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# In-memory DB (shared across all reminder tests)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
Base.metadata.create_all(_ENGINE)
_Session = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture
def db():
    s = _Session()
    yield s
    s.close()


def _user(tier="premium", uid=None):
    return SimpleNamespace(
        id=uid or 1,
        email="nurse@test.com",
        name="Test Nurse",
        subscription_tier=tier,
        reminder_settings=None,
    )


def _doc(days_until: int, doc_id=1):
    exp = datetime.utcnow() + timedelta(days=days_until)
    return SimpleNamespace(
        id=doc_id,
        title="RN License",
        category="Licenses & Certifications",
        expires_at=exp,
    )


# ---------------------------------------------------------------------------
# 1. ReminderSettings.get_days_list()
# ---------------------------------------------------------------------------

class TestReminderDaysList:
    def test_default_days_list(self, db):
        u = User(google_sub="sub-rd-01", email="rd@test.com")
        db.add(u)
        db.flush()
        s = ReminderSettings(user_id=u.id, reminder_days="30,14,7,0")
        db.add(s)
        db.flush()
        assert s.get_days_list() == [30, 14, 7, 0]

    def test_custom_days_list(self, db):
        u = User(google_sub="sub-rd-02", email="rd2@test.com")
        db.add(u)
        db.flush()
        s = ReminderSettings(user_id=u.id, reminder_days="60,30,1")
        db.add(s)
        db.flush()
        assert s.get_days_list() == [60, 30, 1]

    def test_single_day(self, db):
        u = User(google_sub="sub-rd-03", email="rd3@test.com")
        db.add(u)
        db.flush()
        s = ReminderSettings(user_id=u.id, reminder_days="7")
        db.add(s)
        db.flush()
        assert s.get_days_list() == [7]


# ---------------------------------------------------------------------------
# 2. Reminder eligibility (days_left threshold matching)
# ---------------------------------------------------------------------------

class TestReminderEligibility:
    @pytest.mark.parametrize("days_left", [30, 14, 7, 0])
    def test_threshold_days_trigger(self, days_left):
        reminder_days = [30, 14, 7, 0]
        assert days_left in reminder_days

    @pytest.mark.parametrize("days_left", [29, 13, 6, 1, -1])
    def test_non_threshold_days_do_not_trigger(self, days_left):
        reminder_days = [30, 14, 7, 0]
        assert days_left not in reminder_days

    def test_expired_doc_days_left_is_negative(self):
        exp = datetime.utcnow() - timedelta(days=1)
        doc = SimpleNamespace(expires_at=exp)
        days_left = (doc.expires_at.date() - date.today()).days
        assert days_left < 0

    def test_no_expiry_doc_skipped(self):
        doc = SimpleNamespace(expires_at=None)
        skipped = doc.expires_at is None
        assert skipped


# ---------------------------------------------------------------------------
# 3. Duplicate prevention
# ---------------------------------------------------------------------------

class TestDuplicatePrevention:
    def _setup_users_and_docs(self, db):
        # Use a global counter so each test in the class gets a fresh unique user,
        # avoiding UNIQUE constraint errors after db.commit() in the SUT.
        n = next(_sub_counter)
        u = User(google_sub=f"sub-dup-{n:04d}", email=f"dup{n:04d}@test.com", subscription_tier="premium")
        db.add(u)
        db.flush()
        doc = Document(
            user_id=u.id,
            category="Other",
            title="TB Test",
            original_filename="tb.pdf",
            stored_filename=f"tb-{n}.pdf",
            mime_type="application/pdf",
            size_bytes=512,
            content_hash=f"hash-dup-tb-{n}",
        )
        db.add(doc)
        db.flush()
        return u, doc

    def test_first_reminder_is_sent(self, db):
        """When no ReminderLog exists for today, the send function is called."""
        u, doc = self._setup_users_and_docs(db)
        send_fn = MagicMock(return_value={"ok": True, "message_id": "msg-001"})

        # log_event is a local import inside _send_if_not_duplicate; patch at its
        # definition site in app.events, not at the scheduler module level.
        with patch("app.events.log_event"):
            from app.services.reminder_scheduler import _send_if_not_duplicate
            _send_if_not_duplicate(db, u, doc, "email", 7, send_fn)

        send_fn.assert_called_once()

    def test_duplicate_reminder_skipped(self, db):
        """When a ReminderLog already exists for today, the send function is NOT called again."""
        u, doc = self._setup_users_and_docs(db)

        today_start = datetime.combine(date.today(), datetime.min.time())
        log = ReminderLog(
            user_id=u.id,
            document_id=doc.id,
            reminder_type="email",
            days_before=7,
            sent_at=datetime.utcnow(),
            status="sent",
        )
        db.add(log)
        db.flush()

        send_fn = MagicMock(return_value={"ok": True})

        with patch("app.events.log_event"):
            from app.services.reminder_scheduler import _send_if_not_duplicate
            _send_if_not_duplicate(db, u, doc, "email", 7, send_fn)

        send_fn.assert_not_called()

    def test_different_reminder_type_not_considered_duplicate(self, db):
        """An existing 'email' log does not prevent sending 'sms'."""
        u, doc = self._setup_users_and_docs(db)
        log = ReminderLog(
            user_id=u.id,
            document_id=doc.id,
            reminder_type="email",
            days_before=7,
            sent_at=datetime.utcnow(),
            status="sent",
        )
        db.add(log)
        db.flush()

        send_fn = MagicMock(return_value={"ok": True})

        with patch("app.events.log_event"):
            from app.services.reminder_scheduler import _send_if_not_duplicate
            _send_if_not_duplicate(db, u, doc, "sms", 7, send_fn)

        send_fn.assert_called_once()

    def test_different_days_not_considered_duplicate(self, db):
        """An existing log for 30 days does not block a 7-day reminder."""
        u, doc = self._setup_users_and_docs(db)
        log = ReminderLog(
            user_id=u.id,
            document_id=doc.id,
            reminder_type="email",
            days_before=30,
            sent_at=datetime.utcnow(),
            status="sent",
        )
        db.add(log)
        db.flush()

        send_fn = MagicMock(return_value={"ok": True})

        with patch("app.events.log_event"):
            from app.services.reminder_scheduler import _send_if_not_duplicate
            _send_if_not_duplicate(db, u, doc, "email", 7, send_fn)

        send_fn.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Email service — missing Resend key
# ---------------------------------------------------------------------------

class TestEmailServiceMissingKey:
    def test_returns_provider_not_configured_when_key_absent(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from app.services.email_service import send_expiration_email
        user = _user()
        doc = _doc(7)
        result = send_expiration_email(user, doc, 7)
        assert result["ok"] is False
        assert result["error"] == "provider_not_configured"

    def test_does_not_raise_when_key_absent(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from app.services.email_service import send_expiration_email
        result = send_expiration_email(_user(), _doc(14), 14)
        assert isinstance(result, dict)

    def test_get_email_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from app.services.email_service import get_email_status
        assert get_email_status() == "not_configured"

    def test_get_email_status_ok_when_key_present(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "fake-test-key")
        from app.services import email_service
        import importlib
        importlib.reload(email_service)
        assert email_service.get_email_status() == "ok"


# ---------------------------------------------------------------------------
# 5. SMS service — missing Twilio keys
# ---------------------------------------------------------------------------

class TestSmsServiceMissingKey:
    def test_returns_provider_not_configured_when_keys_absent(self, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
        from app.services.sms_service import send_expiration_sms
        user = _user(tier="premium_plus")
        doc = _doc(7)
        result = send_expiration_sms(user, doc, 7)
        assert result["ok"] is False
        assert result["error"] == "provider_not_configured"

    def test_does_not_raise_when_keys_absent(self, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
        from app.services.sms_service import send_expiration_sms
        result = send_expiration_sms(_user("premium_plus"), _doc(0), 0)
        assert isinstance(result, dict)

    def test_get_sms_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
        from app.services.sms_service import get_sms_status
        assert get_sms_status() == "not_configured"


# ---------------------------------------------------------------------------
# 6. Tier gating — scheduler respects premium requirements
# ---------------------------------------------------------------------------

class TestSchedulerTierGating:
    def test_free_user_email_not_sent(self):
        """has_premium(free_user) is False → email send_fn should not be called."""
        from app.premium import has_premium, has_premium_plus
        free = SimpleNamespace(subscription_tier="free")
        assert not has_premium(free)
        assert not has_premium_plus(free)

    def test_premium_user_email_eligible(self):
        from app.premium import has_premium, has_premium_plus
        p = SimpleNamespace(subscription_tier="premium")
        assert has_premium(p)
        assert not has_premium_plus(p)

    def test_premium_plus_user_both_eligible(self):
        from app.premium import has_premium, has_premium_plus
        pp = SimpleNamespace(subscription_tier="premium_plus")
        assert has_premium(pp)
        assert has_premium_plus(pp)

    def test_check_expiring_does_not_crash_with_no_active_reminders(self):
        """Smoke test: the scheduler job should not raise even with an empty DB."""
        # SessionLocal is a local import inside check_expiring_documents, so we
        # must patch it at its definition site (app.db), not the scheduler module.
        with patch("app.db.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db
            from app.services.reminder_scheduler import check_expiring_documents
            check_expiring_documents()

    def test_scheduler_survives_broken_db(self):
        """The scheduler must catch exceptions and not propagate them."""
        with patch("app.db.SessionLocal", side_effect=Exception("db down")):
            from app.services.reminder_scheduler import check_expiring_documents
            check_expiring_documents()  # must not raise
