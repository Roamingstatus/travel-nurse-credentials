"""Outbound email reminders via Resend."""
from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)


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

    html = _build_html(
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

    html = _build_test_html(first_name=first_name, dashboard_url=f"{app_url}/dashboard")

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


def _build_html(*, first_name, doc_title, doc_category, exp_date, days_text, dashboard_url):
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#f4f4f5;margin:0;padding:32px 16px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.08);">
    <div style="background:#4f46e5;padding:24px 32px;">
      <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">Credanta</h1>
      <p style="margin:4px 0 0;color:#c7d2fe;font-size:13px;">Credential Expiration Reminder</p>
    </div>
    <div style="padding:28px 32px;">
      <p style="margin:0 0 16px;font-size:15px;color:#111;">Hi {first_name},</p>
      <p style="margin:0 0 20px;font-size:15px;color:#374151;">
        This is a reminder that your credential <strong>{doc_title}</strong> expires <strong>{days_text}</strong>.
      </p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;margin-bottom:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="color:#6b7280;font-size:13px;padding:4px 0;">Document</td>
            <td style="font-size:14px;font-weight:600;color:#111;text-align:right;">{doc_title}</td>
          </tr>
          <tr>
            <td style="color:#6b7280;font-size:13px;padding:4px 0;">Category</td>
            <td style="font-size:14px;color:#374151;text-align:right;">{doc_category}</td>
          </tr>
          <tr>
            <td style="color:#6b7280;font-size:13px;padding:4px 0;">Expires</td>
            <td style="font-size:14px;font-weight:600;color:#dc2626;text-align:right;">{exp_date}</td>
          </tr>
        </table>
      </div>
      <a href="{dashboard_url}"
         style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
        View Dashboard →
      </a>
      <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;">
        Please log in to Credanta and upload a renewed version before it expires.<br/>
        You are receiving this because you enabled expiration reminders.
      </p>
    </div>
  </div>
</body>
</html>"""


def _build_test_html(*, first_name, dashboard_url):
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#f4f4f5;margin:0;padding:32px 16px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.08);">
    <div style="background:#4f46e5;padding:24px 32px;">
      <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">Credanta</h1>
      <p style="margin:4px 0 0;color:#c7d2fe;font-size:13px;">Test Reminder</p>
    </div>
    <div style="padding:28px 32px;">
      <p style="margin:0 0 16px;font-size:15px;color:#111;">Hi {first_name},</p>
      <p style="margin:0 0 20px;font-size:15px;color:#374151;">
        This is a <strong>test reminder email</strong> from Credanta. Your email reminders are configured correctly!
      </p>
      <p style="margin:0 0 20px;font-size:14px;color:#6b7280;">
        When a credential is approaching its expiration date, you'll receive a message like this with the document name, category, and expiration date.
      </p>
      <a href="{dashboard_url}"
         style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
        Go to Dashboard →
      </a>
    </div>
  </div>
</body>
</html>"""
