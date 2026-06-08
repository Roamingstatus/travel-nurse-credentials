"""Tests for feature access control and environment gating.

Covers all scenarios from the feature-gating spec:
  1. Free user can access: Account, Security, 2FA, Beta feedback
  2. Free user cannot access: Premium email reminders, Packet, Premium+ SMS, Share links, Smart checklist
  3. Premium user can access: Email reminders, Calendar sync, Packet
  4. Premium user cannot access: Premium+ SMS, Premium+ share links, Premium+ agency autofill
  5. Premium+ user can access: all Premium and Premium+ features
  6. Production hides developer subscription tester
  7. Development shows developer subscription tester
  8. Backend returns 403 for unauthorized premium route access
  9. Admin access controlled by ADMIN_EMAILS allowlist
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.premium import (
    can_access_admin_testing,
    can_access_beta_feedback,
    can_access_premium_feature,
    can_access_premium_plus_feature,
    can_access_security_settings,
    can_access_two_step_verification,
    has_premium,
    has_premium_plus,
    is_admin,
    is_development,
    is_production,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _user(tier: str = "free", email: str = "user@example.com"):
    return SimpleNamespace(
        id=1,
        email=email,
        subscription_tier=tier,
        name="Test User",
    )


FREE = _user("free")
PREMIUM = _user("premium")
PREMIUM_PLUS = _user("premium_plus")


# ---------------------------------------------------------------------------
# 1. Free user can access non-premium features
# ---------------------------------------------------------------------------

class TestFreeUserAccess:
    def test_can_access_security_settings(self):
        assert can_access_security_settings(FREE) is True

    def test_can_access_two_step_verification(self):
        assert can_access_two_step_verification(FREE) is True

    def test_can_access_beta_feedback(self):
        assert can_access_beta_feedback(FREE) is True

    def test_anonymous_cannot_access_security(self):
        assert can_access_security_settings(None) is False

    def test_anonymous_cannot_access_2fa(self):
        assert can_access_two_step_verification(None) is False

    def test_anonymous_cannot_access_beta_feedback(self):
        assert can_access_beta_feedback(None) is False


# ---------------------------------------------------------------------------
# 2. Free user cannot access premium features
# ---------------------------------------------------------------------------

class TestFreeUserPremiumGate:
    def test_cannot_access_premium_feature(self):
        assert can_access_premium_feature(FREE) is False

    def test_cannot_access_premium_plus_feature(self):
        assert can_access_premium_plus_feature(FREE) is False

    def test_has_premium_false(self):
        assert has_premium(FREE) is False

    def test_has_premium_plus_false(self):
        assert has_premium_plus(FREE) is False


# ---------------------------------------------------------------------------
# 3. Premium user can access Premium features
# ---------------------------------------------------------------------------

class TestPremiumUserAccess:
    def test_has_premium(self):
        assert has_premium(PREMIUM) is True

    def test_can_access_premium_feature(self):
        assert can_access_premium_feature(PREMIUM) is True

    def test_also_has_security_access(self):
        assert can_access_security_settings(PREMIUM) is True

    def test_also_has_2fa_access(self):
        assert can_access_two_step_verification(PREMIUM) is True


# ---------------------------------------------------------------------------
# 4. Premium user cannot access Premium+ features
# ---------------------------------------------------------------------------

class TestPremiumUserPremiumPlusGate:
    def test_has_premium_plus_false(self):
        assert has_premium_plus(PREMIUM) is False

    def test_cannot_access_premium_plus_feature(self):
        assert can_access_premium_plus_feature(PREMIUM) is False


# ---------------------------------------------------------------------------
# 5. Premium+ user can access everything
# ---------------------------------------------------------------------------

class TestPremiumPlusUserAccess:
    def test_has_premium(self):
        assert has_premium(PREMIUM_PLUS) is True

    def test_has_premium_plus(self):
        assert has_premium_plus(PREMIUM_PLUS) is True

    def test_can_access_premium_feature(self):
        assert can_access_premium_feature(PREMIUM_PLUS) is True

    def test_can_access_premium_plus_feature(self):
        assert can_access_premium_plus_feature(PREMIUM_PLUS) is True

    def test_also_has_security_access(self):
        assert can_access_security_settings(PREMIUM_PLUS) is True

    def test_also_has_beta_feedback_access(self):
        assert can_access_beta_feedback(PREMIUM_PLUS) is True


# ---------------------------------------------------------------------------
# 6 & 7. Environment detection: is_development / is_production
# ---------------------------------------------------------------------------

class TestEnvironmentDetection:
    def test_app_env_development(self):
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            from app import premium as p
            import importlib
            # Re-detect using the function (not cached module-level var)
            env = p._detect_app_env()
            assert env == "development"

    def test_app_env_production(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "production"

    def test_legacy_env_production(self):
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "production"

    def test_legacy_env_development(self):
        with patch.dict(os.environ, {"ENV": "development"}, clear=False):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "development"

    def test_app_env_takes_priority_over_env(self):
        with patch.dict(os.environ, {"APP_ENV": "development", "ENV": "production"}, clear=False):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "development"

    def test_defaults_to_development_when_unset(self):
        env_copy = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "ENV", "REPLIT_DEPLOYMENT_ID", "REPLIT_DEPLOYMENT")}
        with patch.dict(os.environ, env_copy, clear=True):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "development"

    def test_replit_deployment_id_implies_production(self):
        env_copy = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "ENV")}
        env_copy["REPLIT_DEPLOYMENT_ID"] = "deploy-abc-123"
        with patch.dict(os.environ, env_copy, clear=True):
            from app import premium as p
            env = p._detect_app_env()
            assert env == "production"


# ---------------------------------------------------------------------------
# 8. Backend returns 403 for unauthorized premium route access
# ---------------------------------------------------------------------------

class TestBackend403:
    def test_require_premium_raises_403_for_free(self):
        from app.premium import require_premium
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            require_premium(FREE)
        assert exc.value.status_code == 403
        assert "Upgrade" in exc.value.detail

    def test_require_premium_plus_raises_403_for_free(self):
        from app.premium import require_premium_plus
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            require_premium_plus(FREE)
        assert exc.value.status_code == 403

    def test_require_premium_plus_raises_403_for_premium(self):
        from app.premium import require_premium_plus
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            require_premium_plus(PREMIUM)
        assert exc.value.status_code == 403

    def test_require_premium_does_not_raise_for_premium(self):
        from app.premium import require_premium
        require_premium(PREMIUM)  # should not raise

    def test_require_premium_does_not_raise_for_premium_plus(self):
        from app.premium import require_premium
        require_premium(PREMIUM_PLUS)  # should not raise

    def test_require_premium_plus_does_not_raise_for_premium_plus(self):
        from app.premium import require_premium_plus
        require_premium_plus(PREMIUM_PLUS)  # should not raise


# ---------------------------------------------------------------------------
# 9. Admin access controlled by ADMIN_EMAILS allowlist
# ---------------------------------------------------------------------------

class TestAdminAccess:
    def test_admin_user_in_allowlist(self):
        admin_user = _user("free", email="admin@example.com")
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            from app import premium as p
            assert p.is_admin(admin_user) is True

    def test_non_admin_user_not_in_allowlist(self):
        normal_user = _user("premium_plus", email="user@example.com")
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            from app import premium as p
            assert p.is_admin(normal_user) is False

    def test_none_user_is_not_admin(self):
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            from app import premium as p
            assert p.is_admin(None) is False

    def test_can_access_admin_testing_with_email_in_list(self):
        admin_user = _user("free", email="admin@example.com")
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            from app import premium as p
            assert p.can_access_admin_testing(admin_user) is True

    def test_can_access_admin_testing_false_without_email(self):
        normal_user = _user("premium_plus", email="user@example.com")
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            from app import premium as p
            assert p.can_access_admin_testing(normal_user) is False

    def test_no_admin_emails_in_dev_grants_access(self):
        any_user = _user("free")
        env_copy = {k: v for k, v in os.environ.items() if k not in ("ADMIN_EMAILS", "APP_ENV", "ENV", "REPLIT_DEPLOYMENT_ID", "REPLIT_DEPLOYMENT")}
        env_copy["APP_ENV"] = "development"
        with patch.dict(os.environ, env_copy, clear=True):
            from app import premium as p
            p._APP_ENV = "development"
            assert p.is_admin(any_user) is True
            p._APP_ENV = p._detect_app_env()

    def test_no_admin_emails_in_production_denies_access(self):
        any_user = _user("free")
        with patch.dict(os.environ, {"APP_ENV": "production", "ADMIN_EMAILS": ""}):
            from app import premium as p
            p._APP_ENV = "production"
            assert p.is_admin(any_user) is False
            p._APP_ENV = p._detect_app_env()
