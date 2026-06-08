"""Outbound SMS reminders via Twilio (Premium+ only)."""
from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)


def _twilio_configured() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID")
        and os.environ.get("TWILIO_AUTH_TOKEN")
        and os.environ.get("TWILIO_FROM_NUMBER")
    )


def get_sms_status() -> str:
    return "ok" if _twilio_configured() else "not_configured"


def send_expiration_sms(user, document, days_until_expiration: int) -> dict:
    """Send one expiration SMS. Returns {ok, message_id?, error?}."""
    if not _twilio_configured():
        _LOG.warning("[sms] Twilio not configured — SMS not sent")
        return {"ok": False, "error": "provider_not_configured"}

    settings = getattr(user, "reminder_settings", None)
    phone = (
        (settings.phone_number if settings and settings.phone_number else None)
        or getattr(user, "phone_number", None)
    )
    if not phone:
        return {"ok": False, "error": "no_phone_number"}

    app_url = _app_url()

    if days_until_expiration == 0:
        days_text = "today"
    elif days_until_expiration == 1:
        days_text = "tomorrow"
    else:
        days_text = f"in {days_until_expiration} days"

    body = (
        f"Credanta reminder: {document.title} expires {days_text}. "
        f"Log in to update: {app_url}"
    )

    return _send(phone, body)


def send_expired_document_sms(user, document) -> dict:
    """Send an immediate expired-document SMS alert (Premium+ only)."""
    if not _twilio_configured():
        _LOG.warning("[sms] Twilio not configured — expired alert not sent")
        return {"ok": False, "error": "provider_not_configured"}

    settings = getattr(user, "reminder_settings", None)
    phone = (
        (settings.phone_number if settings and settings.phone_number else None)
        or getattr(user, "phone_number", None)
    )
    if not phone:
        return {"ok": False, "error": "no_phone_number"}

    app_url = _app_url()
    body = f"Credanta alert: {document.title} is expired. Log in to update it: {app_url}"
    return _send(phone, body)


def send_test_sms(user) -> dict:
    """Send a test SMS to the user's configured number."""
    if not _twilio_configured():
        return {"ok": False, "error": "provider_not_configured"}

    settings = getattr(user, "reminder_settings", None)
    phone = (
        (settings.phone_number if settings and settings.phone_number else None)
        or getattr(user, "phone_number", None)
    )
    if not phone:
        return {"ok": False, "error": "no_phone_number"}

    app_url = _app_url()
    body = f"Credanta test reminder: SMS is configured correctly. Log in at {app_url}"
    result = _send(phone, body)
    if result.get("ok"):
        result["to"] = phone
    return result


def _send(phone: str, body: str) -> dict:
    try:
        from twilio.rest import Client
    except ImportError:
        _LOG.error("[sms] twilio package not installed")
        return {"ok": False, "error": "twilio_not_installed"}

    try:
        client = Client(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        msg = client.messages.create(
            body=body,
            from_=os.environ["TWILIO_FROM_NUMBER"],
            to=phone,
        )
        _LOG.info("[sms] sent to %s sid=%s", phone, msg.sid)
        return {"ok": True, "message_id": msg.sid}
    except Exception as exc:
        _LOG.error("[sms] failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _app_url() -> str:
    return (
        os.environ.get("APP_BASE_URL")
        or (f"https://{os.environ['REPLIT_DEV_DOMAIN']}" if os.environ.get("REPLIT_DEV_DOMAIN") else "https://credanta.com")
    )
