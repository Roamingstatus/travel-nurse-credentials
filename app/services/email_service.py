"""Outbound email reminders via Resend."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_LOG = logging.getLogger(__name__)

_EMAIL_DIR = Path(__file__).parent.parent / "templates" / "email"
_jinja = Environment(
    loader=FileSystemLoader(str(_EMAIL_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> str:
    return _jinja.get_template(template_name).render(**ctx)


def _resend_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY"))


def get_email_status() -> str:
    return "ok" if _resend_configured() else "not_configured"


def send_expiration_email(user, document, days_until_expiration: int) -> dict:
    """Send one expiration reminder email. Returns {ok, message_id?, error?}."""
    if not _resend_configured():
        _LOG.warning("[email] RESEND_API_KEY not set — email not sent")
        return {"ok": False, "error": "provider_not_configured"}

    try:
        import resend as _resend
    except ImportError:
        _LOG.error("[email] resend package not installed")
        return {"ok": False, "error": "resend_not_installed"}

    _resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ.get("RESEND_FROM_EMAIL", "reminders@credanta.com")
    app_url = _app_url()

    settings = getattr(user, "reminder_settings", None)
    to_email = (
        (settings.reminder_email if settings and settings.reminder_email else None)
        or user.email
    )

    first_name = (user.name or "").split()[0] if user.name else "there"
    exp_date = document.expires_at.strftime("%B %d, %Y") if document.expires_at else "N/A"

    if days_until_expiration == 0:
        days_text = "today"
        subject = f"Credanta Reminder: {document.title} expires today"
    elif days_until_expiration == 1:
        days_text = "tomorrow"
        subject = f"Credanta Reminder: {document.title} expires tomorrow"
    else:
        days_text = f"in {days_until_expiration} days"
        subject = f"Credanta Reminder: {document.title} expires in {days_until_expiration} days"

    html = _render(
        "reminder.html",
        first_name=first_name,
        doc_title=document.title,
        doc_category=document.category,
        exp_date=exp_date,
        days_text=days_text,
        dashboard_url=f"{app_url}/dashboard",
    )

    try:
        resp = _resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        _LOG.info("[email] sent reminder to %s for doc %s (%sd)", to_email, document.id, days_until_expiration)
        return {"ok": True, "message_id": resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)}
    except Exception as exc:
        _LOG.error("[email] failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def send_expired_document_email(user, document) -> dict:
    """Send an immediate expired-document alert email. Returns {ok, message_id?, error?}."""
    if not _resend_configured():
        _LOG.warning("[email] RESEND_API_KEY not set — expired alert not sent")
        return {"ok": False, "error": "provider_not_configured"}

    try:
        import resend as _resend
    except ImportError:
        _LOG.error("[email] resend package not installed")
        return {"ok": False, "error": "resend_not_installed"}

    _resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ.get("RESEND_FROM_EMAIL", "reminders@credanta.com")
    app_url = _app_url()

    settings = getattr(user, "reminder_settings", None)
    to_email = (
        (settings.reminder_email if settings and settings.reminder_email else None)
        or user.email
    )
    first_name = (user.name or "").split()[0] if user.name else "there"
    exp_date = document.expires_at.strftime("%B %d, %Y") if document.expires_at else "N/A"

    html = _render(
        "expired.html",
        first_name=first_name,
        doc_title=document.title,
        doc_category=document.category,
        exp_date=exp_date,
        app_url=app_url,
    )

    try:
        resp = _resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"Credanta Alert: Document expired — {document.title}",
            "html": html,
        })
        _LOG.info("[email] sent expired alert to %s for doc %s", to_email, document.id)
        return {"ok": True, "message_id": resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)}
    except Exception as exc:
        _LOG.error("[email] expired alert failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def send_test_email(user) -> dict:
    """Send a test email with no specific document."""
    if not _resend_configured():
        return {"ok": False, "error": "provider_not_configured"}

    try:
        import resend as _resend
    except ImportError:
        return {"ok": False, "error": "resend_not_installed"}

    _resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ.get("RESEND_FROM_EMAIL", "reminders@credanta.com")
    app_url = _app_url()

    settings = getattr(user, "reminder_settings", None)
    to_email = (
        (settings.reminder_email if settings and settings.reminder_email else None)
        or user.email
    )
    first_name = (user.name or "").split()[0] if user.name else "there"

    html = _render("test.html", first_name=first_name, dashboard_url=f"{app_url}/dashboard")

    try:
        resp = _resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": "Credanta — Test Reminder Email",
            "html": html,
        })
        return {"ok": True, "to": to_email, "message_id": resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)}
    except Exception as exc:
        _LOG.error("[email] test failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _app_url() -> str:
    return (
        os.environ.get("APP_BASE_URL")
        or f"https://{os.environ['REPLIT_DEV_DOMAIN']}"
        if os.environ.get("REPLIT_DEV_DOMAIN")
        else "https://credanta.com"
    )
