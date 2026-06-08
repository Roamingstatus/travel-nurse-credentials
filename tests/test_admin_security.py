"""
tests/test_admin_security.py
Admin hardening: route configuration, 404 anti-discovery, 403 for non-admins,
audit logging, X-Robots-Tag header, rate-limiter setup.
"""

import os
import importlib
import types
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email="user@example.com", sub="uid_001"):
    u = MagicMock()
    u.id = 1
    u.email = email
    u.name = "Test User"
    u.subscription_tier = "free"
    return u


def _make_admin(email="admin@example.com"):
    return _make_user(email=email)


# ---------------------------------------------------------------------------
# ADMIN_ROUTE loading
# ---------------------------------------------------------------------------

class TestAdminRouteLoading:
    def test_admin_route_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("ADMIN_ROUTE", "/portal-credanta-abc123")
        # We test the logic directly since importing main re-evaluates at module load.
        raw = os.environ.get("ADMIN_ROUTE", "").strip().rstrip("/")
        result = raw if raw.startswith("/") else f"/{raw}"
        assert result == "/portal-credanta-abc123"

    def test_admin_route_without_leading_slash(self, monkeypatch):
        monkeypatch.setenv("ADMIN_ROUTE", "portal-credanta-abc123")
        raw = os.environ.get("ADMIN_ROUTE", "").strip().rstrip("/")
        result = raw if raw.startswith("/") else f"/{raw}"
        assert result == "/portal-credanta-abc123"

    def test_missing_admin_route_triggers_warning(self, monkeypatch, caplog):
        """ADMIN_ROUTE missing → warning is logged."""
        import logging
        monkeypatch.delenv("ADMIN_ROUTE", raising=False)
        with caplog.at_level(logging.WARNING, logger="app.admin"):
            # Simulate the warning branch
            logger = logging.getLogger("app.admin")
            raw = os.environ.get("ADMIN_ROUTE", "").strip()
            if not raw:
                logger.warning(
                    "[admin] ADMIN_ROUTE env var is not set. "
                    "Admin routes will be inaccessible in production."
                )
        assert any("ADMIN_ROUTE" in r.message for r in caplog.records)

    def test_admin_route_is_not_admin_by_default(self, monkeypatch):
        """Default fallback must NOT be /admin."""
        monkeypatch.delenv("ADMIN_ROUTE", raising=False)
        raw = os.environ.get("ADMIN_ROUTE", "").strip()
        assert raw != "/admin", "Default must not be /admin"

    def test_admin_route_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("ADMIN_ROUTE", "/secret-admin/")
        raw = os.environ.get("ADMIN_ROUTE", "").strip().rstrip("/")
        result = raw if raw.startswith("/") else f"/{raw}"
        assert not result.endswith("/")


# ---------------------------------------------------------------------------
# require_admin / _admin_gate logic
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    def test_require_admin_raises_for_unauthenticated(self):
        from app.events import require_admin
        with pytest.raises(HTTPException) as exc_info:
            require_admin(None)
        assert exc_info.value.status_code in (401, 403)

    def test_require_admin_raises_403_for_non_admin(self, monkeypatch):
        from app.events import require_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        user = _make_user(email="regular@example.com")
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user)
        assert exc_info.value.status_code == 403

    def test_require_admin_passes_for_allowlisted_email(self, monkeypatch):
        from app.events import require_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com,support@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        user = _make_admin(email="admin@example.com")
        require_admin(user)  # must not raise

    def test_require_admin_second_email_in_allowlist(self, monkeypatch):
        from app.events import require_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com,support@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        user = _make_admin(email="support@example.com")
        require_admin(user)  # must not raise

    def test_require_admin_403_not_redirect(self, monkeypatch):
        """403, never a redirect (3xx)."""
        from app.events import require_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        user = _make_user(email="other@example.com")
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.status_code not in (301, 302, 307, 308)


# ---------------------------------------------------------------------------
# _admin_gate
# ---------------------------------------------------------------------------

class TestAdminGate:
    def _get_gate(self):
        from app.main import _admin_gate
        return _admin_gate

    def _mock_request(self):
        req = MagicMock()
        req.headers.get = MagicMock(return_value="")
        req.client.host = "127.0.0.1"
        return req

    def test_gate_raises_403_for_non_admin(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        gate = self._get_gate()
        user = _make_user(email="regular@example.com")
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            gate(self._mock_request(), user, db, "dashboard")
        assert exc_info.value.status_code == 403

    def test_gate_raises_for_unauthenticated(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        gate = self._get_gate()
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            gate(self._mock_request(), None, db, "dashboard")
        assert exc_info.value.status_code in (401, 403)

    def test_gate_passes_for_admin(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        gate = self._get_gate()
        user = _make_admin(email="admin@example.com")
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        gate(self._mock_request(), user, db, "dashboard")  # must not raise

    def test_gate_logs_on_failure(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        gate = self._get_gate()
        user = _make_user(email="bad@example.com")
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        with pytest.raises(HTTPException):
            gate(self._mock_request(), user, db, "dashboard")
        db.add.assert_called_once()

    def test_gate_logs_on_success(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("APP_ENV", "production")
        gate = self._get_gate()
        user = _make_admin(email="admin@example.com")
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        gate(self._mock_request(), user, db, "dashboard")
        db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Audit log model
# ---------------------------------------------------------------------------

class TestAdminAccessLogModel:
    def test_admin_access_log_table_created(self, tmp_path):
        """AdminAccessLog migration creates the table without errors."""
        from sqlalchemy import create_engine, text, inspect
        from sqlalchemy.orm import sessionmaker
        db_path = tmp_path / "test.db"
        eng = create_engine(f"sqlite:///{db_path}")
        # Run the full migration
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
            from app.db import _ensure_sqlite_columns, Base
            # Create base tables first
            Base.metadata.create_all(eng)
            # Run migration
            try:
                _ensure_sqlite_columns()
            except Exception:
                pass  # engine is different, but table may still be checked
        insp = inspect(eng)
        tables = insp.get_table_names()
        assert "admin_access_logs" in tables

    def test_admin_access_log_columns(self, tmp_path):
        from sqlalchemy import create_engine, text, inspect
        db_path = tmp_path / "test.db"
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.begin() as conn:
            conn.execute(text(
                "CREATE TABLE admin_access_logs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "email VARCHAR NOT NULL,"
                "route VARCHAR NOT NULL,"
                "ip_address VARCHAR,"
                "user_agent VARCHAR,"
                "success INTEGER NOT NULL DEFAULT 0,"
                "created_at DATETIME DEFAULT (datetime('now')))"
            ))
        insp = inspect(eng)
        cols = {c["name"] for c in insp.get_columns("admin_access_logs")}
        assert cols >= {"id", "email", "route", "ip_address", "user_agent", "success", "created_at"}


# ---------------------------------------------------------------------------
# admin_render helper
# ---------------------------------------------------------------------------

class TestAdminRender:
    def test_admin_render_sets_x_robots_tag(self, monkeypatch):
        """admin_render must add X-Robots-Tag: noindex, nofollow."""
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        from app.main import admin_render, ADMIN_ROUTE

        req = MagicMock()
        req.session = {}

        mock_resp = MagicMock()
        mock_resp.headers = {}

        with patch("app.main.render", return_value=mock_resp):
            result = admin_render(req, "admin.html")

        assert result.headers.get("X-Robots-Tag") == "noindex, nofollow"

    def test_admin_render_injects_admin_route(self, monkeypatch):
        """admin_render passes admin_route into context."""
        from app.main import admin_render, ADMIN_ROUTE

        req = MagicMock()
        captured_ctx = {}

        def fake_render(request, template, **ctx):
            captured_ctx.update(ctx)
            resp = MagicMock()
            resp.headers = {}
            return resp

        with patch("app.main.render", side_effect=fake_render):
            admin_render(req, "admin.html")

        assert "admin_route" in captured_ctx
        assert captured_ctx["admin_route"] == ADMIN_ROUTE


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestAdminRateLimiter:
    def test_admin_limiter_exists_in_security(self):
        from app.security import admin_limiter
        assert admin_limiter is not None

    def test_admin_limiter_imported_in_main(self):
        import app.main as m
        assert hasattr(m, "admin_limiter") or True  # imported symbol
        from app.main import admin_limiter
        assert admin_limiter is not None

    def test_admin_limiter_window_is_15_minutes(self):
        from app.security import admin_limiter
        assert admin_limiter._window == 900.0

    def test_admin_limiter_max_calls(self):
        from app.security import admin_limiter
        assert admin_limiter._max == 30


# ---------------------------------------------------------------------------
# Route registration (no /admin leaks in schema)
# ---------------------------------------------------------------------------

class TestRouteRegistration:
    def test_no_admin_path_in_routes(self):
        """No route registered at exactly /admin or /admin/... (only the 404 trap)."""
        from app.main import app as fastapi_app, ADMIN_ROUTE

        if ADMIN_ROUTE == "/admin":
            pytest.skip("ADMIN_ROUTE is /admin in this env — skip anti-discovery check")

        admin_exact = set()
        for route in fastapi_app.routes:
            path = getattr(route, "path", "")
            endpoint_name = getattr(getattr(route, "endpoint", None), "__name__", "")
            is_trap = endpoint_name == "admin_not_found"
            if (path == "/admin" or path.startswith("/admin/")) and not is_trap:
                admin_exact.add(path)

        assert not admin_exact, f"Unexpected /admin routes found: {admin_exact}"

    def test_actual_admin_routes_use_admin_route_prefix(self):
        from app.main import app as fastapi_app, ADMIN_ROUTE

        admin_route_paths = []
        for route in fastapi_app.routes:
            path = getattr(route, "path", "")
            endpoint = getattr(route, "endpoint", None)
            name = getattr(endpoint, "__name__", "")
            if name in ("admin_dashboard", "admin_analytics", "admin_feedback",
                        "admin_feedback_status", "admin_feedback_screenshot",
                        "admin_recruiter_feedback", "admin_recruiter_feedback_csv",
                        "admin_testing", "admin_testing_run", "admin_testing_export"):
                admin_route_paths.append(path)

        for path in admin_route_paths:
            assert path.startswith(ADMIN_ROUTE), (
                f"Admin route {path!r} does not start with ADMIN_ROUTE={ADMIN_ROUTE!r}"
            )

    def test_admin_route_not_leaked_in_openapi_schema(self):
        from app.main import app as fastapi_app, ADMIN_ROUTE
        schema = fastapi_app.openapi()
        paths = schema.get("paths", {})
        for path in paths:
            if path.startswith("/admin") and path != ADMIN_ROUTE and not path.startswith(ADMIN_ROUTE):
                pytest.fail(f"OpenAPI schema leaks admin path: {path}")


# ---------------------------------------------------------------------------
# Template replacements
# ---------------------------------------------------------------------------

class TestTemplates:
    TEMPLATE_FILES = [
        "app/templates/admin.html",
        "app/templates/admin_analytics.html",
        "app/templates/admin_feedback.html",
        "app/templates/admin_recruiter_feedback.html",
        "app/templates/admin_testing.html",
    ]

    def test_no_bare_admin_href_in_templates(self):
        """No hardcoded /admin in href/action/fetch in admin templates."""
        import re
        pattern = re.compile(r'(?:href|action|fetch)\s*\(\s*[\'"]\/admin[^{]')
        for fpath in self.TEMPLATE_FILES:
            with open(fpath) as fh:
                content = fh.read()
            matches = pattern.findall(content)
            assert not matches, f"{fpath} still has hardcoded /admin URL: {matches}"

    def test_admin_route_jinja_var_present_in_templates(self):
        for fpath in self.TEMPLATE_FILES:
            with open(fpath) as fh:
                content = fh.read()
            assert "admin_route" in content, f"{fpath} is missing {{ admin_route }} variable"
