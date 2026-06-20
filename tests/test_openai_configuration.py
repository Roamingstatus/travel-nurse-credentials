import logging

import pytest

from app.security import validate_env
from app.services.openai_service import is_openai_configured


def _set_required_startup_env(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("CLOUDFLARE_TURNSTILE_SITE_KEY", "test-site-key")
    monkeypatch.setenv("CLOUDFLARE_TURNSTILE_SECRET_KEY", "test-secret-key")


def test_is_openai_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_openai_configured() is False

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert is_openai_configured() is True


def test_startup_warns_in_development_when_openai_key_missing(monkeypatch, caplog):
    _set_required_startup_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with caplog.at_level(logging.WARNING, logger="credanta.security"):
        validate_env()

    assert "OPENAI_API_KEY is missing" in caplog.text
    assert "test-key" not in caplog.text


def test_startup_fails_in_production_when_openai_key_missing(monkeypatch):
    _set_required_startup_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
        validate_env()


def test_startup_succeeds_when_openai_key_exists(monkeypatch):
    _set_required_startup_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    validate_env()

