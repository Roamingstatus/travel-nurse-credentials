"""
Tests for app/services/security_monitor.py

Covers:
- _safe_meta: sensitive-key masking and truncation
- _sliding: in-memory sliding-window bucket logic
- record_* detection helpers: threshold triggering
- log_security_event: DB row creation + no-crash guarantee
- _maybe_alert: no crash when env vars absent
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, SecurityEvent
from app.services.security_monitor import (
    _safe_meta,
    _sliding,
    log_security_event,
    record_admin_probe,
    record_login_failure,
    record_server_error,
    record_share_token_invalid,
    record_upload_rejected,
)

# ---------------------------------------------------------------------------
# In-memory DB fixture (isolated per-test)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mem_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def mem_db(mem_engine):
    connection = mem_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_request(ip: str = "1.2.3.4", path: str = "/test", method: str = "GET") -> MagicMock:
    req = MagicMock()
    _header_data = {"User-Agent": "pytest/1.0", "X-Forwarded-For": ip}
    req.headers = MagicMock()
    req.headers.get = lambda k, d="": _header_data.get(k, d)
    req.client = MagicMock(host=ip)
    req.url = MagicMock(path=path)
    req.method = method
    return req


# ---------------------------------------------------------------------------
# _safe_meta
# ---------------------------------------------------------------------------

class TestSafeMeta:
    def test_empty_returns_empty(self):
        assert _safe_meta({}) == {}

    def test_none_returns_empty(self):
        assert _safe_meta(None) == {}  # type: ignore[arg-type]

    def test_sensitive_keys_masked(self):
        meta = {"token": "abc123", "password": "s3cr3t", "description": "ok"}
        result = _safe_meta(meta)
        assert result["token"] == "***"
        assert result["password"] == "***"
        assert result["description"] == "ok"

    def test_partial_sensitive_key_match(self):
        meta = {"access_token": "secret_value", "api_key": "key123"}
        result = _safe_meta(meta)
        assert result["access_token"] == "***"
        assert result["api_key"] == "***"

    def test_long_string_truncated(self):
        long_val = "x" * 600
        result = _safe_meta({"msg": long_val})
        assert len(result["msg"]) < 600
        assert "truncated" in result["msg"]

    def test_short_string_not_truncated(self):
        result = _safe_meta({"msg": "hello"})
        assert result["msg"] == "hello"

    def test_non_string_values_preserved(self):
        result = _safe_meta({"count": 42, "flag": True})
        assert result["count"] == 42
        assert result["flag"] is True


# ---------------------------------------------------------------------------
# _sliding
# ---------------------------------------------------------------------------

class TestSliding:
    def setup_method(self):
        from collections import defaultdict
        self.bucket: dict = defaultdict(list)

    def test_first_hit_returns_one(self):
        hits = _sliding(self.bucket, "k1", window=60)
        assert len(hits) == 1

    def test_accumulates_within_window(self):
        for _ in range(4):
            _sliding(self.bucket, "k2", window=60)
        hits = _sliding(self.bucket, "k2", window=60)
        assert len(hits) == 5

    def test_expired_hits_excluded(self):
        import time as _time
        self.bucket["k3"] = [_time.monotonic() - 999]
        hits = _sliding(self.bucket, "k3", window=60)
        assert len(hits) == 1


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

class TestRecordAdminProbe:
    def setup_method(self):
        # Reset the module-level bucket between tests
        from app.services import security_monitor as sm
        sm._probe_hits.clear()

    def test_below_threshold_returns_false(self):
        req = _fake_request(ip="10.0.0.1")
        for _ in range(4):
            result = record_admin_probe(req)
        assert result is False

    def test_at_threshold_returns_true(self):
        req = _fake_request(ip="10.0.0.2")
        for _ in range(5):
            result = record_admin_probe(req)
        assert result is True

    def test_different_ips_independent(self):
        r1 = _fake_request(ip="10.1.1.1")
        r2 = _fake_request(ip="10.1.1.2")
        for _ in range(5):
            record_admin_probe(r1)
        # r2 only has 1 hit
        result2 = record_admin_probe(r2)
        assert result2 is False


class TestRecordLoginFailure:
    def setup_method(self):
        from app.services import security_monitor as sm
        sm._login_fails.clear()

    def test_below_threshold_returns_false(self):
        req = _fake_request(ip="10.0.0.3")
        for _ in range(4):
            result = record_login_failure(req, email="user@test.com")
        assert result is False

    def test_at_threshold_returns_true(self):
        req = _fake_request(ip="10.0.0.4")
        for _ in range(5):
            result = record_login_failure(req, email="user@test.com")
        assert result is True

    def test_no_email_uses_ip_only(self):
        req = _fake_request(ip="10.0.0.5")
        for _ in range(5):
            result = record_login_failure(req)
        assert result is True


class TestRecordShareTokenInvalid:
    def setup_method(self):
        from app.services import security_monitor as sm
        sm._share_abuse.clear()

    def test_below_threshold_returns_false(self):
        req = _fake_request(ip="10.0.0.6")
        for _ in range(9):
            result = record_share_token_invalid(req)
        assert result is False

    def test_at_threshold_returns_true(self):
        req = _fake_request(ip="10.0.0.7")
        for _ in range(10):
            result = record_share_token_invalid(req)
        assert result is True


class TestRecordUploadRejected:
    def setup_method(self):
        from app.services import security_monitor as sm
        sm._upload_abuse.clear()

    def test_below_threshold_returns_false(self):
        req = _fake_request(ip="10.0.0.8")
        for _ in range(9):
            result = record_upload_rejected(req, user_id=1)
        assert result is False

    def test_at_threshold_returns_true(self):
        req = _fake_request(ip="10.0.0.9")
        for _ in range(10):
            result = record_upload_rejected(req, user_id=2)
        assert result is True

    def test_no_user_id_uses_ip(self):
        req = _fake_request(ip="10.0.0.10")
        for _ in range(10):
            result = record_upload_rejected(req)
        assert result is True


class TestRecordServerError:
    def setup_method(self):
        from app.services import security_monitor as sm
        sm._srv_errors.clear()

    def test_below_threshold_returns_false(self):
        for _ in range(4):
            result = record_server_error("/api/endpoint")
        assert result is False

    def test_at_threshold_returns_true(self):
        for _ in range(5):
            result = record_server_error("/api/other")
        assert result is True

    def test_different_routes_independent(self):
        for _ in range(5):
            record_server_error("/route/a")
        result = record_server_error("/route/b")
        assert result is False


# ---------------------------------------------------------------------------
# log_security_event
# ---------------------------------------------------------------------------

class TestLogSecurityEvent:
    def test_creates_db_row(self, mem_db):
        req = _fake_request(ip="5.5.5.5", path="/documents/1/edit")

        mem_db.close = lambda: None
        with patch("app.db.SessionLocal", return_value=mem_db):
            log_security_event(
                "unauthorized_data_access", "medium", req,
                metadata={"doc_id": 1, "route": "edit"},
            )

        ev = mem_db.query(SecurityEvent).filter_by(event_type="unauthorized_data_access").first()
        assert ev is not None
        assert ev.severity == "medium"
        assert ev.ip_address == "5.5.5.5"
        assert ev.route == "/documents/1/edit"
        assert ev.resolved is False

    def test_does_not_raise_on_db_error(self):
        req = _fake_request()
        bad_session = MagicMock()
        bad_session.add.side_effect = Exception("DB down")

        with patch("app.db.SessionLocal", return_value=bad_session):
            # Must not raise — security_monitor swallows all exceptions
            log_security_event("server_error", "high", req)

    def test_user_attributes_stored(self, mem_db):
        req = _fake_request(ip="6.6.6.6")
        user = MagicMock(id=42, email="nurse@example.com")

        mem_db.close = lambda: None
        with patch("app.db.SessionLocal", return_value=mem_db):
            log_security_event("admin_access_denied", "medium", req, user=user)

        ev = mem_db.query(SecurityEvent).filter_by(event_type="admin_access_denied").first()
        assert ev is not None
        assert ev.user_id == 42
        assert ev.email == "nurse@example.com"

    def test_sensitive_metadata_masked(self, mem_db):
        import json
        req = _fake_request()

        mem_db.close = lambda: None
        with patch("app.db.SessionLocal", return_value=mem_db):
            log_security_event(
                "upload_rejected", "low", req,
                metadata={"token": "secret123", "filename": "test.pdf"},
            )

        ev = mem_db.query(SecurityEvent).filter_by(event_type="upload_rejected").first()
        assert ev is not None
        stored = json.loads(ev.request_metadata)
        assert stored["token"] == "***"
        assert stored["filename"] == "test.pdf"


# ---------------------------------------------------------------------------
# _maybe_alert: no-crash guarantee
# ---------------------------------------------------------------------------

class TestMaybeAlert:
    def test_no_crash_without_env_vars(self):
        from app.services.security_monitor import _maybe_alert
        # Should not raise even with no SECURITY_ALERT_EMAIL set
        _maybe_alert("admin_probe_detected", "critical", "1.2.3.4", None, {})

    def test_no_crash_without_resend_key(self):
        from app.services.security_monitor import _maybe_alert
        with patch.dict("os.environ", {"SECURITY_ALERT_EMAIL": "admin@example.com"}):
            # RESEND_API_KEY absent — should warn but not raise
            _maybe_alert("unauthorized_data_access", "high", "1.2.3.4", "u@e.com", {"doc_id": 1})

    def test_low_severity_non_alert_type_skipped(self):
        from app.services.security_monitor import _maybe_alert
        with patch("app.services.security_monitor._LOG") as mock_log:
            with patch.dict("os.environ", {
                "SECURITY_ALERT_EMAIL": "admin@example.com",
                "RESEND_API_KEY": "re_fake",
            }):
                # "rate_limit_triggered" at "low" severity should be skipped silently
                _maybe_alert("rate_limit_triggered", "low", "1.2.3.4", None, {})
                # No send attempted, no error log
                mock_log.warning.assert_not_called()
