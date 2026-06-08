"""Tests for subscription tier gating on premium and premium+ routes."""
import pytest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Document, ReminderSettings, ShareLink, User, get_session
from app.main import app

# ---------------------------------------------------------------------------
# Shared in-memory DB — set up once for all HTTP tests.
# StaticPool ensures every new session reuses the SAME underlying connection,
# so tables created by create_all() are visible to later sessions.
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
Base.metadata.create_all(_ENGINE)
_SessionFactory = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


def _db_override():
    s = _SessionFactory()
    try:
        yield s
    finally:
        s.close()


app.dependency_overrides[get_session] = _db_override


def _make_test_user(tier: str) -> User:
    """Insert a real User row and return the persisted object."""
    db = _SessionFactory()
    existing = db.query(User).filter_by(google_sub=f"sub-{tier}").first()
    if existing:
        db.close()
        db2 = _SessionFactory()
        user = db2.get(User, existing.id)
        db2.close()
        return user
    user = User(
        google_sub=f"sub-{tier}",
        email=f"{tier}@test.com",
        name=f"Test {tier}",
        subscription_tier=tier,
    )
    db.add(user)
    db.commit()
    uid = user.id
    db.close()
    db2 = _SessionFactory()
    obj = db2.get(User, uid)
    db2.close()
    return obj


_FREE_USER = _make_test_user("free")
_PREMIUM_USER = _make_test_user("premium")
_PREMIUM_PLUS_USER = _make_test_user("premium_plus")

# Shared TestClient — follows redirects by default (needed for "allowed" tests).
_CLIENT = TestClient(app, raise_server_exceptions=False)
# No-redirect client used when testing that a route is blocked via 302/303/307/403.
_CLIENT_NR = TestClient(app, raise_server_exceptions=False, follow_redirects=False)


def _get(url: str, user: User) -> int:
    with patch("app.main.require_user", return_value=user), \
         patch("app.main.current_user", return_value=user):
        return _CLIENT.get(url).status_code


def _get_blocked(url: str, user: User) -> int:
    """Returns the raw (non-followed) status code to detect redirect- or 403-gated routes."""
    with patch("app.main.require_user", return_value=user), \
         patch("app.main.current_user", return_value=user):
        return _CLIENT_NR.get(url).status_code


def _post(url: str, user: User, data: dict | None = None) -> int:
    with patch("app.main.require_user", return_value=user), \
         patch("app.main.current_user", return_value=user):
        return _CLIENT.post(url, data=data or {}).status_code


# ---------------------------------------------------------------------------
# Tier helper unit tests
# ---------------------------------------------------------------------------

class TestTierHelpers:
    def test_has_premium_free(self):
        from app.premium import has_premium
        assert not has_premium(SimpleNamespace(subscription_tier="free"))

    def test_has_premium_premium(self):
        from app.premium import has_premium
        assert has_premium(SimpleNamespace(subscription_tier="premium"))

    def test_has_premium_premium_plus(self):
        from app.premium import has_premium
        assert has_premium(SimpleNamespace(subscription_tier="premium_plus"))

    def test_has_premium_plus_free(self):
        from app.premium import has_premium_plus
        assert not has_premium_plus(SimpleNamespace(subscription_tier="free"))

    def test_has_premium_plus_premium(self):
        from app.premium import has_premium_plus
        assert not has_premium_plus(SimpleNamespace(subscription_tier="premium"))

    def test_has_premium_plus_premium_plus(self):
        from app.premium import has_premium_plus
        assert has_premium_plus(SimpleNamespace(subscription_tier="premium_plus"))

    def test_require_premium_raises_for_free(self):
        from fastapi import HTTPException
        from app.premium import require_premium
        with pytest.raises(HTTPException) as exc:
            require_premium(SimpleNamespace(subscription_tier="free"))
        assert exc.value.status_code == 403

    def test_require_premium_passes_for_premium(self):
        from app.premium import require_premium
        require_premium(SimpleNamespace(subscription_tier="premium"))

    def test_require_premium_passes_for_premium_plus(self):
        from app.premium import require_premium
        require_premium(SimpleNamespace(subscription_tier="premium_plus"))

    def test_require_premium_plus_raises_for_free(self):
        from fastapi import HTTPException
        from app.premium import require_premium_plus
        with pytest.raises(HTTPException) as exc:
            require_premium_plus(SimpleNamespace(subscription_tier="free"))
        assert exc.value.status_code == 403

    def test_require_premium_plus_raises_for_premium(self):
        from fastapi import HTTPException
        from app.premium import require_premium_plus
        with pytest.raises(HTTPException) as exc:
            require_premium_plus(SimpleNamespace(subscription_tier="premium"))
        assert exc.value.status_code == 403

    def test_require_premium_plus_passes_for_premium_plus(self):
        from app.premium import require_premium_plus
        require_premium_plus(SimpleNamespace(subscription_tier="premium_plus"))

    def test_none_user_is_not_premium(self):
        from app.premium import has_premium, has_premium_plus
        assert not has_premium(None)
        assert not has_premium_plus(None)

    def test_backward_compat_user_has_premium(self):
        from app.premium import user_has_premium
        assert user_has_premium(SimpleNamespace(subscription_tier="premium"))
        assert not user_has_premium(SimpleNamespace(subscription_tier="free"))


# ---------------------------------------------------------------------------
# Free user: premium/premium+ routes return 403; free routes return 200
# ---------------------------------------------------------------------------

class TestFreeUserBlocked:
    def test_packet_blocked(self):
        # /packet redirects free users to /premium (302) rather than raising 403
        assert _get_blocked("/packet", _FREE_USER) in (302, 303, 307, 403)

    def test_packet_pdf_blocked(self):
        # /packet/pdf redirects free users to /premium (302) rather than raising 403
        assert _get_blocked("/packet/pdf", _FREE_USER) in (302, 303, 307, 403)

    def test_calendar_blocked(self):
        assert _get("/premium/calendar/export", _FREE_USER) == 403

    def test_reminders_settings_blocked(self):
        assert _get("/premium/reminders/settings", _FREE_USER) == 403

    def test_resume_enhance_blocked(self):
        assert _get("/premium/resume/enhance", _FREE_USER) == 403

    def test_share_blocked(self):
        # /share redirects non-premium-plus users to /premium (302) rather than 403
        assert _get_blocked("/share", _FREE_USER) in (302, 303, 307, 403)

    def test_checklist_blocked(self):
        assert _get("/premium-plus/checklist", _FREE_USER) == 403

    def test_agency_packet_blocked(self):
        assert _get("/premium-plus/agency-packet/autofill", _FREE_USER) == 403

    def test_share_create_blocked(self):
        assert _post("/share/create", _FREE_USER, {"label": "test", "expires_days": ""}) == 403

    def test_dashboard_still_accessible(self):
        assert _get("/dashboard", _FREE_USER) == 200

    def test_documents_still_accessible(self):
        assert _get("/documents", _FREE_USER) == 200

    def test_premium_page_still_accessible(self):
        assert _get("/premium", _FREE_USER) == 200


# ---------------------------------------------------------------------------
# Premium user: premium features pass; premium+ features are still 403
# ---------------------------------------------------------------------------

class TestPremiumUserAccess:
    def test_packet_allowed(self):
        # empty vault → redirect (302), not 403
        assert _get("/packet", _PREMIUM_USER) != 403

    def test_calendar_blocked_for_premium(self):
        # Calendar feed is a Premium Plus feature; plain premium users get 403
        assert _get("/premium/calendar/export", _PREMIUM_USER) == 403

    def test_reminders_settings_allowed(self):
        assert _get("/premium/reminders/settings", _PREMIUM_USER) == 200

    def test_resume_enhance_allowed(self):
        assert _get("/premium/resume/enhance", _PREMIUM_USER) == 200

    def test_share_blocked_for_premium(self):
        # /share redirects plain-premium users to /premium (302), not 403
        assert _get_blocked("/share", _PREMIUM_USER) in (302, 303, 307, 403)

    def test_share_create_blocked_for_premium(self):
        assert _post("/share/create", _PREMIUM_USER, {"label": "t"}) == 403

    def test_checklist_blocked_for_premium(self):
        assert _get("/premium-plus/checklist", _PREMIUM_USER) == 403

    def test_agency_packet_blocked_for_premium(self):
        assert _get("/premium-plus/agency-packet/autofill", _PREMIUM_USER) == 403

    def test_premium_packet_generate_allowed(self):
        assert _get("/premium/packet/generate", _PREMIUM_USER) != 403


# ---------------------------------------------------------------------------
# Premium+ user: all features pass
# ---------------------------------------------------------------------------

class TestPremiumPlusUserAccess:
    def test_packet_allowed(self):
        assert _get("/packet", _PREMIUM_PLUS_USER) != 403

    def test_calendar_allowed(self):
        assert _get("/premium/calendar/export", _PREMIUM_PLUS_USER) != 403

    def test_reminders_settings_allowed(self):
        assert _get("/premium/reminders/settings", _PREMIUM_PLUS_USER) == 200

    def test_resume_enhance_allowed(self):
        assert _get("/premium/resume/enhance", _PREMIUM_PLUS_USER) == 200

    def test_share_allowed(self):
        assert _get("/share", _PREMIUM_PLUS_USER) == 200

    def test_checklist_allowed(self):
        assert _get("/premium-plus/checklist", _PREMIUM_PLUS_USER) == 200

    def test_agency_packet_allowed(self):
        assert _get("/premium-plus/agency-packet/autofill", _PREMIUM_PLUS_USER) == 200


# ---------------------------------------------------------------------------
# Checklist logic unit tests
# ---------------------------------------------------------------------------

class TestChecklistLogic:
    def _doc(self, category, expires_at=None):
        return SimpleNamespace(category=category, expires_at=expires_at, title=category)

    def test_missing_all_when_no_docs(self):
        from app.checklist import generate_checklist
        result = generate_checklist("Healthcare", [])
        assert "Identity" in result["missing"]
        assert "Licenses & Certifications" in result["missing"]
        assert "Health & Compliance" in result["missing"]

    def test_required_categories_complete(self):
        from app.checklist import generate_checklist
        from datetime import datetime, timedelta
        docs = [
            self._doc("Identity"),
            self._doc("Licenses & Certifications", expires_at=datetime.utcnow() + timedelta(days=200)),
            self._doc("Health & Compliance"),
        ]
        result = generate_checklist("Healthcare", docs)
        # all three required categories should NOT be missing
        for cat in result["required_categories"]:
            assert cat not in result["missing"], f"Required category {cat!r} is unexpectedly missing"

    def test_readiness_score_zero_when_all_required_missing(self):
        from app.checklist import generate_checklist
        result = generate_checklist("Healthcare", [])
        assert result["readiness_score"] == 0

    def test_readiness_score_100_when_required_complete(self):
        from app.checklist import generate_checklist
        from datetime import datetime, timedelta
        docs = [
            self._doc("Identity"),
            self._doc("Licenses & Certifications", expires_at=datetime.utcnow() + timedelta(days=200)),
            self._doc("Health & Compliance"),
        ]
        result = generate_checklist("Healthcare", docs)
        assert result["readiness_score"] == 100

    def test_expired_doc_goes_to_expired_bucket(self):
        from app.checklist import generate_checklist
        from datetime import datetime, timedelta
        docs = [
            self._doc("Identity"),
            self._doc("Licenses & Certifications", expires_at=datetime.utcnow() - timedelta(days=10)),
        ]
        result = generate_checklist("Healthcare", docs)
        assert "Licenses & Certifications" in result["expired"]

    def test_expiring_soon_goes_to_expiring_bucket(self):
        from app.checklist import generate_checklist
        from datetime import datetime, timedelta
        docs = [
            self._doc("Identity"),
            self._doc("Licenses & Certifications", expires_at=datetime.utcnow() + timedelta(days=14)),
            self._doc("Health & Compliance"),
        ]
        result = generate_checklist("Healthcare", docs)
        assert "Licenses & Certifications" in result["expiring"]

    def test_profile_names_not_empty(self):
        from app.checklist import PROFILE_NAMES
        assert len(PROFILE_NAMES) > 0


# ---------------------------------------------------------------------------
# Agency packet logic unit tests
# ---------------------------------------------------------------------------

class TestAgencyPacketLogic:
    def _doc(self, category, expires_at=None):
        return SimpleNamespace(category=category, expires_at=expires_at, title=category)

    def test_all_missing_when_no_docs(self):
        from app.agency_packet import autofill_agency_packet
        result = autofill_agency_packet("Healthcare Credentialing", [])
        assert "Identity" in result["missing"]

    def test_all_matched_when_docs_present(self):
        from app.agency_packet import autofill_agency_packet
        from datetime import datetime, timedelta
        docs = [
            self._doc("Identity"),
            self._doc("Licenses & Certifications", expires_at=datetime.utcnow() + timedelta(days=200)),
            self._doc("Health & Compliance"),
        ]
        result = autofill_agency_packet("Healthcare Credentialing", docs)
        assert "Identity" in result["matched"]
        assert result["readiness_pct"] == 100

    def test_zero_readiness_when_empty(self):
        from app.agency_packet import autofill_agency_packet
        result = autofill_agency_packet("Healthcare Credentialing", [])
        assert result["readiness_pct"] == 0

    def test_doc_mapping_populated(self):
        from app.agency_packet import autofill_agency_packet
        docs = [self._doc("Identity")]
        result = autofill_agency_packet("General Employment", docs)
        assert "Identity" in result["doc_mapping"]

    def test_template_names_not_empty(self):
        from app.agency_packet import TEMPLATE_NAMES
        assert len(TEMPLATE_NAMES) > 0
