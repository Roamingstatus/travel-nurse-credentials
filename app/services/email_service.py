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


def send_password_reset_email(to_email: str, display_name: str, reset_url: str) -> dict:
    """Send a password-reset link to the user.

    If Resend is not configured the call is a no-op and returns ok=False —
    callers should handle this gracefully (the reset token is still valid;
    the user can also be shown the link in development).
    """
    if not _resend_configured():
        _LOG.warning("[email] send_password_reset_email: Resend not configured; skipping.")
        return {"ok": False, "error": "provider_not_configured"}

    try:
        import resend as _resend
    except ImportError:
        return {"ok": False, "error": "resend_not_installed"}

    _resend.api_key = os.environ["RESEND_API_KEY"]
    from_email = os.environ.get("RESEND_FROM_EMAIL", "noreply@credanta.com")
    first_name = (display_name or "").split()[0] if display_name else "there"

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px 16px;color:#1f2937">
  <img src="https://credanta.com/static/credanta-logo-full.png" alt="Credanta" style="height:32px;margin-bottom:24px"/>
  <h2 style="margin:0 0 12px;font-size:20px">Reset your Credanta password</h2>
  <p style="color:#4b5563;line-height:1.6">Hi {first_name},</p>
  <p style="color:#4b5563;line-height:1.6">We received a request to reset your password.
     Click the button below to choose a new one. This link expires in 1 hour.</p>
  <div style="text-align:center;margin:28px 0">
    <a href="{reset_url}"
       style="background:#4f46e5;color:#fff;padding:12px 28px;border-radius:8px;
              text-decoration:none;font-weight:600;font-size:15px;display:inline-block">
      Reset password
    </a>
  </div>
  <p style="color:#6b7280;font-size:13px;line-height:1.6">
    If you didn't request this, you can safely ignore this email — your password will not change.
  </p>
  <p style="color:#9ca3af;font-size:12px;margin-top:24px">
    Credanta &middot; <a href="https://credanta.com" style="color:#9ca3af">credanta.com</a>
  </p>
</body>
</html>"""

    try:
        resp = _resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": "Reset your Credanta password",
            "html": html,
        })
        _LOG.info("[email] password reset sent to %s", to_email)
        return {"ok": True, "message_id": resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)}
    except Exception as exc:
        _LOG.error("[email] password reset failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _app_url() -> str:
    return (
        os.environ.get("APP_BASE_URL")
        or f"https://{os.environ['REPLIT_DEV_DOMAIN']}"
        if os.environ.get("REPLIT_DEV_DOMAIN")
        else "https://credanta.com"
    )
