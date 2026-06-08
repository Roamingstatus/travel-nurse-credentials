"""Integration tests for the recruiter feedback API.

Routes under test:
  POST /api/recruiter-feedback/opened  — event log (fire-and-forget)
  POST /api/recruiter-feedback          — validated feedback submission
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.db import Base, get_session
from app.main import app, _RTF_ROLE_TYPES, _RTF_TIMINGS, _RTF_AGENCY_TYPES
from app.security import feedback_limiter


# ---------------------------------------------------------------------------
# Rate-limiter isolation: clear the in-process bucket before every test so
# tests that run after the first 5 submissions don't inherit a depleted limit.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # Reset bucket state and temporarily raise the call cap so bulk-validation
    # tests (which POST many times in one test) don't hit the 5/min limit.
    feedback_limiter._buckets.clear()
    original_max = feedback_limiter._max
    feedback_limiter._max = 10_000
    yield
    feedback_limiter._max = original_max
    feedback_limiter._buckets.clear()


# ---------------------------------------------------------------------------
# Shared in-memory DB
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
Base.metadata.create_all(_ENGINE)

# recruiter_template_feedback is created via raw SQL at app startup (not an ORM
# model), so we must create it manually in the test database.
from sqlalchemy import text as _text
with _ENGINE.begin() as _conn:
    _conn.execute(_text(
        "CREATE TABLE IF NOT EXISTS recruiter_template_feedback ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  share_token_id INTEGER REFERENCES share_links(id) ON DELETE SET NULL,"
        "  role_type VARCHAR NOT NULL,"
        "  required_documents TEXT NOT NULL DEFAULT '[]',"
        "  timing VARCHAR NOT NULL,"
        "  agency_type VARCHAR NOT NULL,"
        "  optional_email VARCHAR,"
        "  user_agent VARCHAR,"
        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    ))

_Session = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


def _db_override():
    s = _Session()
    try:
        yield s
    finally:
        s.close()


_CLIENT = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# DB-override isolation: set the override per-test so that other test modules
# that also write app.dependency_overrides[get_session] (e.g. test_tiers) do
# not bleed into these tests when the full suite runs.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_db_override():
    app.dependency_overrides[get_session] = _db_override
    yield
    app.dependency_overrides.pop(get_session, None)

# Valid payload that passes all validation
_VALID_PAYLOAD = {
    "share_token": "",
    "role_type": _RTF_ROLE_TYPES[0],
    "required_documents": ["BLS", "State License"],
    "timing": _RTF_TIMINGS[0],
    "agency_type": _RTF_AGENCY_TYPES[0],
    "cf_token": "bypass",
}


def _post(payload: dict):
    """POST to /api/recruiter-feedback with Turnstile bypassed."""
    with patch("app.main.verify_turnstile", return_value=True):
        return _CLIENT.post(
            "/api/recruiter-feedback",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )


# ---------------------------------------------------------------------------
# /api/recruiter-feedback/opened
# ---------------------------------------------------------------------------

class TestFeedbackOpened:
    def test_opened_returns_200(self):
        resp = _CLIENT.post(
            "/api/recruiter-feedback/opened",
            content=json.dumps({"share_token": ""}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    def test_opened_returns_ok_true(self):
        resp = _CLIENT.post(
            "/api/recruiter-feedback/opened",
            content=json.dumps({"share_token": ""}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.json().get("ok") is True

    def test_opened_with_unknown_token_still_200(self):
        resp = _CLIENT.post(
            "/api/recruiter-feedback/opened",
            content=json.dumps({"share_token": "totally-unknown-token"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    def test_opened_with_empty_body_does_not_crash(self):
        resp = _CLIENT.post(
            "/api/recruiter-feedback/opened",
            content=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    def test_opened_with_malformed_json_returns_200(self):
        resp = _CLIENT.post(
            "/api/recruiter-feedback/opened",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/recruiter-feedback — valid submission
# ---------------------------------------------------------------------------

class TestFeedbackSubmitValid:
    def test_valid_payload_returns_200(self):
        assert _post(_VALID_PAYLOAD).status_code == 200

    def test_valid_payload_returns_ok_true(self):
        data = _post(_VALID_PAYLOAD).json()
        assert data.get("ok") is True

    def test_all_role_types_accepted(self):
        for role in _RTF_ROLE_TYPES:
            payload = {**_VALID_PAYLOAD, "role_type": role}
            assert _post(payload).status_code == 200, f"Role '{role}' was rejected"

    def test_all_timing_types_accepted(self):
        for timing in _RTF_TIMINGS:
            payload = {**_VALID_PAYLOAD, "timing": timing}
            assert _post(payload).status_code == 200, f"Timing '{timing}' was rejected"

    def test_all_agency_types_accepted(self):
        for agency in _RTF_AGENCY_TYPES:
            payload = {**_VALID_PAYLOAD, "agency_type": agency}
            assert _post(payload).status_code == 200, f"Agency type '{agency}' was rejected"

    def test_empty_required_documents_accepted(self):
        payload = {**_VALID_PAYLOAD, "required_documents": []}
        assert _post(payload).status_code == 200

    def test_optional_email_accepted(self):
        payload = {**_VALID_PAYLOAD, "optional_email": "recruiter@agency.com"}
        assert _post(payload).status_code == 200

    def test_optional_email_omitted_accepted(self):
        payload = {**_VALID_PAYLOAD}
        payload.pop("optional_email", None)
        assert _post(payload).status_code == 200


# ---------------------------------------------------------------------------
# /api/recruiter-feedback — field validation
# ---------------------------------------------------------------------------

class TestFeedbackSubmitValidation:
    def test_missing_role_type_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "role_type"}
        assert _post(payload).status_code == 422

    def test_missing_timing_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "timing"}
        assert _post(payload).status_code == 422

    def test_missing_agency_type_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "agency_type"}
        assert _post(payload).status_code == 422

    def test_invalid_role_type_returns_422(self):
        payload = {**_VALID_PAYLOAD, "role_type": "Hacker"}
        assert _post(payload).status_code == 422

    def test_invalid_timing_returns_422(self):
        payload = {**_VALID_PAYLOAD, "timing": "Whenever I feel like it"}
        assert _post(payload).status_code == 422

    def test_invalid_agency_type_returns_422(self):
        payload = {**_VALID_PAYLOAD, "agency_type": "Criminal Org"}
        assert _post(payload).status_code == 422

    def test_invalid_json_returns_400(self):
        with patch("app.main.verify_turnstile", return_value=True):
            resp = _CLIENT.post(
                "/api/recruiter-feedback",
                content=b"not json at all",
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 400

    def test_documents_filtered_to_allow_list(self):
        """Unknown document names are silently filtered out — request still succeeds."""
        payload = {
            **_VALID_PAYLOAD,
            "required_documents": ["BLS", "UNKNOWN_DOC_XYZ", "State License"],
        }
        assert _post(payload).status_code == 200

    def test_document_list_capped_at_50(self):
        """More than 50 document entries should not cause a 500."""
        payload = {**_VALID_PAYLOAD, "required_documents": ["BLS"] * 200}
        resp = _post(payload)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/recruiter-feedback — Turnstile bot protection
# ---------------------------------------------------------------------------

class TestFeedbackTurnstileProtection:
    def test_turnstile_failure_returns_403(self):
        with patch("app.main.verify_turnstile", return_value=False):
            resp = _CLIENT.post(
                "/api/recruiter-feedback",
                content=json.dumps(_VALID_PAYLOAD),
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 403

    def test_turnstile_failure_error_message(self):
        with patch("app.main.verify_turnstile", return_value=False):
            resp = _CLIENT.post(
                "/api/recruiter-feedback",
                content=json.dumps(_VALID_PAYLOAD),
                headers={"Content-Type": "application/json"},
            )
        assert "bot" in resp.text.lower() or "protection" in resp.text.lower() or "verify" in resp.text.lower()

    def test_empty_cf_token_blocked_when_turnstile_configured(self):
        """When verify_turnstile is strict, empty token must be rejected."""
        payload = {**_VALID_PAYLOAD, "cf_token": ""}
        with patch("app.main.verify_turnstile", return_value=False):
            resp = _CLIENT.post(
                "/api/recruiter-feedback",
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Allow-list constants — sanity checks
# ---------------------------------------------------------------------------

class TestAllowListConstants:
    def test_role_types_not_empty(self):
        assert len(_RTF_ROLE_TYPES) > 0

    def test_timings_not_empty(self):
        assert len(_RTF_TIMINGS) > 0

    def test_agency_types_not_empty(self):
        assert len(_RTF_AGENCY_TYPES) > 0

    def test_travel_nurse_in_role_types(self):
        assert "Travel Nurse" in _RTF_ROLE_TYPES

    def test_no_duplicates_in_role_types(self):
        assert len(_RTF_ROLE_TYPES) == len(set(_RTF_ROLE_TYPES))

    def test_no_duplicates_in_timings(self):
        assert len(_RTF_TIMINGS) == len(set(_RTF_TIMINGS))

    def test_no_duplicates_in_agency_types(self):
        assert len(_RTF_AGENCY_TYPES) == len(set(_RTF_AGENCY_TYPES))
