"""Tests for document expiration status logic."""
from datetime import datetime, timedelta

import pytest

from app.dashboard import (
    EXPIRING_WINDOW_DAYS,
    days_until,
    status_for,
    summarize,
    ui_status_label,
)
from types import SimpleNamespace

# Fixed reference time used across all tests
NOW = datetime(2025, 6, 1, 12, 0, 0)


def _doc(expires_at=None):
    return SimpleNamespace(
        expires_at=expires_at,
        issued_at=None,
        title="Test Doc",
        category="Other",
        created_at=NOW,
    )


class TestStatusFor:
    def test_no_expiry_returns_no_expiry(self):
        assert status_for(_doc(expires_at=None), NOW) == "no-expiry"

    def test_past_date_returns_expired(self):
        d = _doc(expires_at=NOW - timedelta(days=1))
        assert status_for(d, NOW) == "expired"

    def test_expired_long_ago(self):
        d = _doc(expires_at=NOW - timedelta(days=365))
        assert status_for(d, NOW) == "expired"

    def test_expires_today_is_expired(self):
        d = _doc(expires_at=NOW - timedelta(seconds=1))
        assert status_for(d, NOW) == "expired"

    def test_expires_within_window_is_expiring(self):
        d = _doc(expires_at=NOW + timedelta(days=30))
        assert status_for(d, NOW) == "expiring"

    def test_expires_at_boundary_is_expiring(self):
        d = _doc(expires_at=NOW + timedelta(days=EXPIRING_WINDOW_DAYS - 1))
        assert status_for(d, NOW) == "expiring"

    def test_expires_just_past_window_is_current(self):
        d = _doc(expires_at=NOW + timedelta(days=EXPIRING_WINDOW_DAYS + 1))
        assert status_for(d, NOW) == "current"

    def test_expires_far_future_is_current(self):
        d = _doc(expires_at=NOW + timedelta(days=365))
        assert status_for(d, NOW) == "current"

    def test_uses_utcnow_when_no_now_given(self):
        """Smoke test: calling without explicit now should not raise."""
        d = _doc(expires_at=datetime(2099, 1, 1))
        assert status_for(d) in ("current", "expiring", "expired", "no-expiry")


class TestUiStatusLabel:
    def test_expired_label(self):
        d = _doc(expires_at=NOW - timedelta(days=1))
        assert ui_status_label(d, NOW) == "expired"

    def test_expiring_label(self):
        d = _doc(expires_at=NOW + timedelta(days=10))
        assert ui_status_label(d, NOW) == "expiring_soon"

    def test_current_label(self):
        d = _doc(expires_at=NOW + timedelta(days=200))
        assert ui_status_label(d, NOW) == "valid"

    def test_no_expiry_label(self):
        assert ui_status_label(_doc(), NOW) == "valid"


class TestDaysUntil:
    def test_returns_none_for_no_expiry(self):
        assert days_until(_doc(), NOW) is None

    def test_positive_for_future_date(self):
        d = _doc(expires_at=NOW + timedelta(days=30))
        assert days_until(d, NOW) == 30

    def test_negative_for_past_date(self):
        d = _doc(expires_at=NOW - timedelta(days=5))
        assert days_until(d, NOW) == -5

    def test_zero_on_exact_expiry_day(self):
        d = _doc(expires_at=NOW)
        assert days_until(d, NOW) == 0


class TestSummarize:
    def _make_docs(self):
        # summarize() calls datetime.utcnow() internally, so anchor relative to real now
        real_now = datetime.utcnow()
        return [
            _doc(expires_at=real_now - timedelta(days=10)),   # expired
            _doc(expires_at=real_now - timedelta(days=1)),    # expired
            _doc(expires_at=real_now + timedelta(days=20)),   # expiring
            _doc(expires_at=real_now + timedelta(days=200)),  # current
            _doc(expires_at=None),                            # no-expiry
        ]

    def test_total_count(self):
        docs = self._make_docs()
        result = summarize(docs)
        assert result["total"] == 5

    def test_expired_count(self):
        docs = self._make_docs()
        result = summarize(docs)
        assert len(result["expired"]) == 2

    def test_expiring_count(self):
        docs = self._make_docs()
        result = summarize(docs)
        assert len(result["expiring"]) == 1

    def test_current_count(self):
        docs = self._make_docs()
        result = summarize(docs)
        assert len(result["current"]) == 1

    def test_no_expiry_count(self):
        docs = self._make_docs()
        result = summarize(docs)
        assert len(result["no_expiry"]) == 1

    def test_empty_list(self):
        result = summarize([])
        assert result["total"] == 0
        assert result["expired"] == []
        assert result["expiring"] == []
        assert result["current"] == []
        assert result["no_expiry"] == []

    def test_recent_capped_at_six(self):
        docs = [_doc() for _ in range(10)]
        result = summarize(docs)
        assert len(result["recent"]) <= 6
